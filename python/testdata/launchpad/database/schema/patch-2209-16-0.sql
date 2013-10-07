-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE BugTaskFlat (
    bugtask integer PRIMARY KEY,
    bug integer NOT NULL,
    datecreated timestamp without time zone,
    duplicateof integer,
    bug_owner integer NOT NULL,
    fti ts2.tsvector,
    information_type integer NOT NULL,
    date_last_updated timestamp without time zone NOT NULL,
    heat integer NOT NULL,
    product integer,
    productseries integer,
    distribution integer,
    distroseries integer,
    sourcepackagename integer,
    status integer NOT NULL,
    importance integer NOT NULL,
    assignee integer,
    milestone integer,
    owner integer NOT NULL,
    active boolean NOT NULL,
    access_policies integer[],
    access_grants integer[]
);


-- Non-target-specific filters
CREATE INDEX bugtaskflat__bug__idx ON BugTaskFlat USING btree (bug);

CREATE INDEX bugtaskflat__bug_owner__idx
    ON BugTaskFlat USING btree (bug_owner);
CREATE INDEX bugtaskflat__owner__idx
    ON BugTaskFlat USING btree (owner);
CREATE INDEX bugtaskflat__assignee__idx
    ON BugTaskFlat USING btree (assignee);
CREATE INDEX bugtaskflat__milestone__idx
    ON BugTaskFlat USING btree (milestone);

CREATE INDEX bugtaskflat__fti__idx ON BugTaskFlat USING gist (fti);


-- Distribution-wide sorts
CREATE INDEX
    bugtaskflat__distribution__date_last_updated__idx
    ON bugtaskflat
    USING btree (distribution, date_last_updated)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__datecreated__idx
    ON bugtaskflat
    USING btree (distribution, datecreated)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__heat__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, heat, bugtask DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__importance__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, importance, bugtask DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__status__bugtask__idx
    ON bugtaskflat
    USING btree (distribution, status, bugtask DESC)
    WHERE distribution IS NOT NULL;

-- DSP or packageless sorts
CREATE INDEX
    bugtaskflat__distribution__spn__date_last_updated__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, date_last_updated)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__datecreated__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, datecreated)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__heat__bug__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, heat, bug DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__importance__bug__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, importance, bug DESC)
    WHERE distribution IS NOT NULL;
CREATE INDEX
    bugtaskflat__distribution__spn__status__bug__idx
    ON bugtaskflat
    USING btree (distribution, sourcepackagename, status, bug DESC)
    WHERE distribution IS NOT NULL;


-- DistroSeries-wide sorts
CREATE INDEX
    bugtaskflat__distroseries__date_last_updated__idx
    ON bugtaskflat
    USING btree (distroseries, date_last_updated)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__datecreated__idx
    ON bugtaskflat
    USING btree (distroseries, datecreated)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__heat__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, heat, bugtask DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__importance__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, importance, bugtask DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__status__bugtask__idx
    ON bugtaskflat
    USING btree (distroseries, status, bugtask DESC)
    WHERE distroseries IS NOT NULL;

-- SP or packageless sorts
CREATE INDEX
    bugtaskflat__distroseries__spn__date_last_updated__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, date_last_updated)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__datecreated__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, datecreated)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__heat__bug__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, heat, bug DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__importance__bug__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, importance, bug DESC)
    WHERE distroseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__distroseries__spn__status__bug__idx
    ON bugtaskflat
    USING btree (distroseries, sourcepackagename, status, bug DESC)
    WHERE distroseries IS NOT NULL;


-- Product sorts
CREATE INDEX
    bugtaskflat__product__date_last_updated__idx
    ON bugtaskflat
    USING btree (product, date_last_updated)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__datecreated__idx
    ON bugtaskflat
    USING btree (product, datecreated)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__heat__bug__idx
    ON bugtaskflat
    USING btree (product, heat, bug DESC)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__importance__bug__idx
    ON bugtaskflat
    USING btree (product, importance, bug DESC)
    WHERE product IS NOT NULL;
CREATE INDEX
    bugtaskflat__product__status__bug__idx
    ON bugtaskflat
    USING btree (product, status, bug DESC)
    WHERE product IS NOT NULL;

-- ProductSeries sorts
CREATE INDEX
    bugtaskflat__productseries__date_last_updated__idx
    ON bugtaskflat
    USING btree (productseries, date_last_updated)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__datecreated__idx
    ON bugtaskflat
    USING btree (productseries, datecreated)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__heat__bug__idx
    ON bugtaskflat
    USING btree (productseries, heat, bug DESC)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__importance__bug__idx
    ON bugtaskflat
    USING btree (productseries, importance, bug DESC)
    WHERE productseries IS NOT NULL;
CREATE INDEX
    bugtaskflat__productseries__status__bug__idx
    ON bugtaskflat
    USING btree (productseries, status, bug DESC)
    WHERE productseries IS NOT NULL;


-- Update helpers

CREATE OR REPLACE FUNCTION bug_build_access_cache(bug_id integer,
                                                  information_type integer)
    RETURNS record
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    _access_artifact integer;
    _access_policies integer[];
    _access_grants integer[];
    cache record;
BEGIN
    -- If the bug is private, grab the access control information.
    -- If the bug is public, access_policies and access_grants are NULL.
    -- 3 == PRIVATESECURITY, 4 == USERDATA, 5 == PROPRIETARY
    IF information_type IN (3, 4, 5) THEN
        SELECT id INTO _access_artifact
            FROM accessartifact
            WHERE bug = bug_id;
        -- We have to do the order in a subquery until 9.0 (8.4 doesn't
        -- support ordering within an aggregate).
        SELECT COALESCE(array_agg(policy), ARRAY[]::integer[])
            INTO _access_policies
            FROM (
                SELECT policy FROM
                accesspolicyartifact
                WHERE artifact = _access_artifact
                ORDER BY policy) AS policies;
        SELECT COALESCE(array_agg(grantee), ARRAY[]::integer[])
            INTO _access_grants
            FROM (
                SELECT grantee FROM
                accessartifactgrant
                WHERE artifact = _access_artifact
                ORDER BY grantee) AS grantees;
    END IF;
    cache := (_access_policies, _access_grants);
    RETURN cache;
END;
$$;

COMMENT ON FUNCTION bug_build_access_cache(bug_id integer,
                                           information_type integer) IS
    'Build an access cache for the given bug. Returns '
    '({AccessPolicyArtifact.policy}, {AccessArtifactGrant.grantee}) '
    'for private bugs, or (NULL, NULL) for public ones.';


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
           _access_grants
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
                access_grants = new_flat_row.access_grants
                WHERE bugtask = new_flat_row.bugtask;
        END IF;
        RETURN FALSE;
    ELSE
        RETURN TRUE;
    END IF;
END;
$$;

COMMENT ON FUNCTION bugtask_flatten(task_id integer, check_only boolean) IS
    'Create or update a BugTaskFlat row from the source tables. Returns '
    'whether the row was up to date. If check_only is true, the row is not '
    'brought up to date.';


CREATE OR REPLACE FUNCTION bug_flatten_access(bug_id integer)
    RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    _information_type integer;
    _access_policies integer[];
    _access_grants integer[];
BEGIN
    SELECT information_type FROM bug INTO _information_type WHERE id = bug_id;
    SELECT policies, grants
        INTO _access_policies, _access_grants
        FROM bug_build_access_cache(bug_id, _information_type)
            AS (policies integer[], grants integer[]);
    UPDATE bugtaskflat
        SET
            access_policies = _access_policies,
            access_grants = _access_grants
        WHERE bug = bug_id;
    RETURN;
END;
$$;

COMMENT ON FUNCTION bug_flatten_access(bug_id integer) IS
    'Recalculate the access cache on a bug''s flattened tasks.';


CREATE OR REPLACE FUNCTION accessartifact_flatten_bug(artifact_id integer)
    RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    bug_id integer;
BEGIN
    SELECT bug INTO bug_id FROM accessartifact WHERE id = artifact_id;
    IF bug_id IS NOT NULL THEN
        PERFORM bug_flatten_access(bug_id);
    END IF;
    RETURN;
END;
$$;

COMMENT ON FUNCTION accessartifact_flatten_bug(artifact_id integer) IS
    'If the access artifact is a bug, update the access cache on its '
    'flattened tasks.';



-- BugTask trigger.

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
            OR NEW.owner IS DISTINCT FROM OLD.owner) THEN
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
                owner = NEW.owner
                WHERE bugtask = NEW.id;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM bugtask_flatten(OLD.id, FALSE);
    END IF;
    RETURN NULL;
END;
$$;

-- z so they happen after fti and access updates.
CREATE TRIGGER z_bugtask_maintain_bugtaskflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON bugtask
    FOR EACH ROW EXECUTE PROCEDURE bugtask_maintain_bugtaskflat_trig();



-- Bug trigger. Only UPDATE, since on INSERT or DELETE there are no tasks.

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
        OR NEW.heat IS DISTINCT FROM OLD.heat) THEN
        UPDATE bugtaskflat
            SET
                duplicateof = NEW.duplicateof,
                bug_owner = NEW.owner,
                fti = NEW.fti,
                information_type = NEW.information_type,
                date_last_updated = NEW.date_last_updated,
                heat = NEW.heat
            WHERE bug = OLD.id;
    END IF;

    IF NEW.information_type IS DISTINCT FROM OLD.information_type THEN
        PERFORM bug_flatten_access(OLD.id);
    END IF;
    RETURN NULL;
END;
$$;

-- z so they happen after fti and access updates.
CREATE TRIGGER z_bug_maintain_bugtaskflat_trigger
    AFTER UPDATE ON bug
    FOR EACH ROW EXECUTE PROCEDURE bug_maintain_bugtaskflat_trig();



-- Shared AccessPolicyArtifact and AccessArtifactGrant trigger.

CREATE OR REPLACE FUNCTION accessartifact_maintain_bugtaskflat_trig()
    RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM accessartifact_flatten_bug(NEW.artifact);
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM accessartifact_flatten_bug(NEW.artifact);
        IF OLD.artifact != NEW.artifact THEN
            PERFORM accessartifact_flatten_bug(OLD.artifact);
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM accessartifact_flatten_bug(OLD.artifact);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER accesspolicyartifact_maintain_bugtaskflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accesspolicyartifact
    FOR EACH ROW EXECUTE PROCEDURE accessartifact_maintain_bugtaskflat_trig();

CREATE TRIGGER accessartifactgrant_maintain_bugtaskflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accessartifactgrant
    FOR EACH ROW EXECUTE PROCEDURE accessartifact_maintain_bugtaskflat_trig();

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 0);
