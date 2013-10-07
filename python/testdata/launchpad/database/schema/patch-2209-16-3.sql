-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE BugTaskFlat ADD COLUMN
    latest_patch_uploaded timestamp without time zone;
ALTER TABLE BugTaskFlat ADD COLUMN
    date_closed timestamp without time zone;


CREATE OR REPLACE FUNCTION bugtask_flatten(task_id integer, check_only boolean)
    RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    bug_row Bug%ROWTYPE;
    task_row BugTask%ROWTYPE;
    old_flat_row BugTaskFlat%ROWTYPE;
    new_flat_row BugTaskFlat%ROWTYPE;
    _product_active boolean;
    _access_policies integer[];
    _access_grants integer[];
BEGIN
    -- This is the master function to update BugTaskFlat, but there are
    -- maintenance triggers and jobs on the involved tables that update
    -- it directly. Any changes here probably require a corresponding
    -- change in other trigger functions.

    SELECT * INTO task_row FROM BugTask WHERE id = task_id;
    SELECT * INTO old_flat_row FROM BugTaskFlat WHERE bugtask = task_id;

    -- If the task doesn't exist, ensure that there's no flat row.
    IF task_row.id IS NULL THEN
        IF old_flat_row.bugtask IS NOT NULL THEN
            IF NOT check_only THEN
                DELETE FROM BugTaskFlat WHERE bugtask = task_id;
            END IF;
            RETURN FALSE;
        ELSE
            RETURN TRUE;
        END IF;
    END IF;

    SELECT * FROM bug INTO bug_row WHERE id = task_row.bug;

    -- If it's a product(series) task, we must consult the active flag.
    IF task_row.product IS NOT NULL THEN
        SELECT product.active INTO _product_active
            FROM product WHERE product.id = task_row.product LIMIT 1;
    ELSIF task_row.productseries IS NOT NULL THEN
        SELECT product.active INTO _product_active
            FROM
                product
                JOIN productseries ON productseries.product = product.id
            WHERE productseries.id = task_row.productseries LIMIT 1;
    END IF;

    SELECT policies, grants
        INTO _access_policies, _access_grants
        FROM bug_build_access_cache(bug_row.id, bug_row.information_type)
            AS (policies integer[], grants integer[]);

    -- Compile the new flat row.
    SELECT task_row.id, bug_row.id, task_row.datecreated,
           bug_row.duplicateof, bug_row.owner, bug_row.fti,
           bug_row.information_type, bug_row.date_last_updated,
           bug_row.heat, task_row.product, task_row.productseries,
           task_row.distribution, task_row.distroseries,
           task_row.sourcepackagename, task_row.status,
           task_row.importance, task_row.assignee,
           task_row.milestone, task_row.owner,
           COALESCE(_product_active, TRUE),
           _access_policies,
           _access_grants,
           bug_row.latest_patch_uploaded, task_row.date_closed
           INTO new_flat_row;

    -- Calculate the necessary updates.
    IF old_flat_row.bugtask IS NULL THEN
        IF NOT check_only THEN
            INSERT INTO BugTaskFlat VALUES (new_flat_row.*);
        END IF;
        RETURN FALSE;
    ELSIF new_flat_row != old_flat_row THEN
        IF NOT check_only THEN
            UPDATE BugTaskFlat SET
                bug = new_flat_row.bug,
                datecreated = new_flat_row.datecreated,
                duplicateof = new_flat_row.duplicateof,
                bug_owner = new_flat_row.bug_owner,
                fti = new_flat_row.fti,
                information_type = new_flat_row.information_type,
                date_last_updated = new_flat_row.date_last_updated,
                heat = new_flat_row.heat,
                product = new_flat_row.product,
                productseries = new_flat_row.productseries,
                distribution = new_flat_row.distribution,
                distroseries = new_flat_row.distroseries,
                sourcepackagename = new_flat_row.sourcepackagename,
                status = new_flat_row.status,
                importance = new_flat_row.importance,
                assignee = new_flat_row.assignee,
                milestone = new_flat_row.milestone,
                owner = new_flat_row.owner,
                active = new_flat_row.active,
                access_policies = new_flat_row.access_policies,
                access_grants = new_flat_row.access_grants,
                date_closed = new_flat_row.date_closed,
                latest_patch_uploaded = new_flat_row.latest_patch_uploaded
                WHERE bugtask = new_flat_row.bugtask;
        END IF;
        RETURN FALSE;
    ELSE
        RETURN TRUE;
    END IF;
END;
$$;


CREATE OR REPLACE FUNCTION bugtask_maintain_bugtaskflat_trig() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bugtask_flatten(NEW.id, FALSE);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.bug != OLD.bug THEN
            RAISE EXCEPTION 'cannot move bugtask to a different bug';
        ELSIF (NEW.product IS DISTINCT FROM OLD.product
            OR NEW.productseries IS DISTINCT FROM OLD.productseries) THEN
            -- product.active may differ. Do a full update.
            PERFORM bugtask_flatten(NEW.id, FALSE);
        ELSIF (
            NEW.datecreated IS DISTINCT FROM OLD.datecreated
            OR NEW.product IS DISTINCT FROM OLD.product
            OR NEW.productseries IS DISTINCT FROM OLD.productseries
            OR NEW.distribution IS DISTINCT FROM OLD.distribution
            OR NEW.distroseries IS DISTINCT FROM OLD.distroseries
            OR NEW.sourcepackagename IS DISTINCT FROM OLD.sourcepackagename
            OR NEW.status IS DISTINCT FROM OLD.status
            OR NEW.importance IS DISTINCT FROM OLD.importance
            OR NEW.assignee IS DISTINCT FROM OLD.assignee
            OR NEW.milestone IS DISTINCT FROM OLD.milestone
            OR NEW.owner IS DISTINCT FROM OLD.owner
            OR NEW.date_closed IS DISTINCT FROM OLD.date_closed) THEN
            -- Otherwise just update the columns from bugtask.
            -- Access policies and grants may have changed due to target
            -- transitions, but an earlier trigger will already have
            -- mirrored them to all relevant flat tasks.
            UPDATE BugTaskFlat SET
                datecreated = NEW.datecreated,
                product = NEW.product,
                productseries = NEW.productseries,
                distribution = NEW.distribution,
                distroseries = NEW.distroseries,
                sourcepackagename = NEW.sourcepackagename,
                status = NEW.status,
                importance = NEW.importance,
                assignee = NEW.assignee,
                milestone = NEW.milestone,
                owner = NEW.owner,
                date_closed = NEW.date_closed
                WHERE bugtask = NEW.id;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM bugtask_flatten(OLD.id, FALSE);
    END IF;
    RETURN NULL;
END;
$$;


CREATE OR REPLACE FUNCTION bug_maintain_bugtaskflat_trig() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF (
        NEW.duplicateof IS DISTINCT FROM OLD.duplicateof
        OR NEW.owner IS DISTINCT FROM OLD.owner
        OR NEW.fti IS DISTINCT FROM OLD.fti
        OR NEW.information_type IS DISTINCT FROM OLD.information_type
        OR NEW.date_last_updated IS DISTINCT FROM OLD.date_last_updated
        OR NEW.heat IS DISTINCT FROM OLD.heat
        OR NEW.latest_patch_uploaded IS DISTINCT FROM
            OLD.latest_patch_uploaded) THEN
        UPDATE bugtaskflat
            SET
                duplicateof = NEW.duplicateof,
                bug_owner = NEW.owner,
                fti = NEW.fti,
                information_type = NEW.information_type,
                date_last_updated = NEW.date_last_updated,
                heat = NEW.heat,
                latest_patch_uploaded = NEW.latest_patch_uploaded
            WHERE bug = OLD.id;
    END IF;

    IF NEW.information_type IS DISTINCT FROM OLD.information_type THEN
        PERFORM bug_flatten_access(OLD.id);
    END IF;
    RETURN NULL;
END;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 3);
