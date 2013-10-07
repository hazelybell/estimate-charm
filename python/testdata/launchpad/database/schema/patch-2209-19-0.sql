-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Journal functions. Speed is critical -- these are run by appservers.

ALTER TABLE bugsummary ALTER COLUMN fixed_upstream SET DEFAULT false;
ALTER TABLE bugsummaryjournal ALTER COLUMN fixed_upstream SET DEFAULT false;

ALTER TABLE bugsummary ADD COLUMN access_policy integer;
ALTER TABLE bugsummaryjournal ADD COLUMN access_policy integer;

CREATE OR REPLACE FUNCTION public.bug_summary_flush_temp_journal()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- May get called even though no summaries were made (for simplicity in the
    -- callers). We sum the rows here to minimise the number of inserts
    -- into the persistent journal, as it's reasonably likely that we'll
    -- have -1s and +1s cancelling each other out.
    PERFORM ensure_bugsummary_temp_journal();
    INSERT INTO BugSummaryJournal(
        count, product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream,
        access_policy)
    SELECT
        SUM(count), product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream,
        access_policy
    FROM bugsummary_temp_journal
    GROUP BY
        product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream,
        access_policy
    HAVING SUM(count) != 0;
    TRUNCATE bugsummary_temp_journal;
END;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_journal_bugtaskflat(btf_row bugtaskflat, _count integer)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    PERFORM ensure_bugsummary_temp_journal();
    INSERT INTO BugSummary_Temp_Journal(
        count, product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream,
        access_policy)
    SELECT
        _count, product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream,
        access_policy
        FROM bugsummary_locations(btf_row);
END;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_journal_bug(bug_row bug, _count integer)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    btf_row bugtaskflat%ROWTYPE;
BEGIN
    FOR btf_row IN SELECT * FROM bugtaskflat WHERE bug = bug_row.id
    LOOP
        PERFORM bugsummary_journal_bugtaskflat(btf_row, _count);
    END LOOP;
END;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_locations(btf_row bugtaskflat)
 RETURNS SETOF bugsummary
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF btf_row.duplicateof IS NOT NULL THEN
        RETURN;
    END IF;
    RETURN QUERY
        SELECT
            CAST(NULL AS integer) AS id,
            CAST(1 AS integer) AS count,
            bug_targets.product, bug_targets.productseries,
            bug_targets.distribution, bug_targets.distroseries,
            bug_targets.sourcepackagename,
            bug_viewers.viewed_by, bug_tags.tag, btf_row.status,
            btf_row.milestone, btf_row.importance,
            btf_row.latest_patch_uploaded IS NOT NULL AS has_patch,
            false AS fixed_upstream, NULL::integer AS access_policy
        FROM
            bugsummary_targets(btf_row) as bug_targets,
            bugsummary_tags(btf_row) AS bug_tags,
            bugsummary_viewers(btf_row) AS bug_viewers;
END;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_tags(btf_row bugtaskflat)
 RETURNS SETOF bugtag
 LANGUAGE sql
 STABLE
AS $function$
    SELECT * FROM BugTag WHERE BugTag.bug = $1.bug
    UNION ALL
    SELECT NULL::integer, $1.bug, NULL::text;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_targets(btf_row bugtaskflat)
 RETURNS TABLE(
    product integer, productseries integer, distribution integer,
    distroseries integer, sourcepackagename integer)
 LANGUAGE sql
 IMMUTABLE
AS $function$
    -- Include a sourcepackagename-free task if this one has a
    -- sourcepackagename, so package tasks are also counted in their
    -- distro/series.
    SELECT
        $1.product, $1.productseries, $1.distribution,
        $1.distroseries, $1.sourcepackagename
    UNION -- Implicit DISTINCT
    SELECT
        $1.product, $1.productseries, $1.distribution,
        $1.distroseries, NULL;
$function$;

CREATE OR REPLACE FUNCTION public.bugsummary_viewers(btf_row bugtaskflat)
 RETURNS TABLE(viewed_by integer)
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT NULL WHERE $1.information_type IN (1, 2)
    UNION ALL
    SELECT unnest($1.access_grants)
    WHERE $1.information_type IN (3, 4, 5);
$function$;

CREATE OR REPLACE FUNCTION public.bugtag_maintain_bug_summary()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO public
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(NEW.bug);
        ELSE
            PERFORM summarise_bug(NEW.bug);
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(OLD.bug);
        ELSE
            PERFORM summarise_bug(OLD.bug);
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN OLD;
    ELSE
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(OLD.bug);
            IF OLD.bug <> NEW.bug THEN
                PERFORM unsummarise_bug(NEW.bug);
            END IF;
        ELSE
            PERFORM summarise_bug(OLD.bug);
            IF OLD.bug <> NEW.bug THEN
                PERFORM summarise_bug(NEW.bug);
            END IF;
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.bugtaskflat_maintain_bug_summary()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO public
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bugsummary_journal_bugtaskflat(NEW, 1);
        PERFORM bug_summary_flush_temp_journal();
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM bugsummary_journal_bugtaskflat(OLD, -1);
        PERFORM bug_summary_flush_temp_journal();
    ELSIF
        NEW.product IS DISTINCT FROM OLD.product
        OR NEW.productseries IS DISTINCT FROM OLD.productseries
        OR NEW.distribution IS DISTINCT FROM OLD.distribution
        OR NEW.distroseries IS DISTINCT FROM OLD.distroseries
        OR NEW.sourcepackagename IS DISTINCT FROM OLD.sourcepackagename
        OR NEW.status IS DISTINCT FROM OLD.status
        OR NEW.milestone IS DISTINCT FROM OLD.milestone
        OR NEW.importance IS DISTINCT FROM OLD.importance
        OR NEW.latest_patch_uploaded IS DISTINCT FROM OLD.latest_patch_uploaded
        OR NEW.information_type IS DISTINCT FROM OLD.information_type
        OR NEW.access_grants IS DISTINCT FROM OLD.access_grants
        OR NEW.access_policies IS DISTINCT FROM OLD.access_policies
    THEN
        PERFORM bugsummary_journal_bugtaskflat(OLD, -1);
        PERFORM bugsummary_journal_bugtaskflat(NEW, 1);
        PERFORM bug_summary_flush_temp_journal();
    END IF;
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION public.ensure_bugsummary_temp_journal()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    CREATE TEMPORARY TABLE bugsummary_temp_journal (
        LIKE bugsummary ) ON COMMIT DROP;
    ALTER TABLE bugsummary_temp_journal ALTER COLUMN id DROP NOT NULL;
EXCEPTION
    WHEN duplicate_table THEN
        NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION public.summarise_bug(bug integer)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    PERFORM bugsummary_journal_bug(bug_row(bug), 1);
END;
$function$;

CREATE OR REPLACE FUNCTION public.unsummarise_bug(bug integer)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    PERFORM bugsummary_journal_bug(bug_row(bug), -1);
END;
$function$;


-- Rollup functions. Speed isn't critical, as it's done post-request by garbo.

CREATE OR REPLACE FUNCTION public.bugsummary_rollup_journal(batchsize integer DEFAULT NULL::integer)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO public
AS $function$
DECLARE
    d bugsummary%ROWTYPE;
    max_id integer;
BEGIN
    -- Lock so we don't content with other invokations of this
    -- function. We can happily lock the BugSummary table for writes
    -- as this function is the only thing that updates that table.
    -- BugSummaryJournal remains unlocked so nothing should be blocked.
    LOCK TABLE BugSummary IN ROW EXCLUSIVE MODE;

    IF batchsize IS NULL THEN
        SELECT MAX(id) INTO max_id FROM BugSummaryJournal;
    ELSE
        SELECT MAX(id) INTO max_id FROM (
            SELECT id FROM BugSummaryJournal ORDER BY id LIMIT batchsize
            ) AS Whatever;
    END IF;

    FOR d IN
        SELECT
            NULL as id,
            SUM(count),
            product,
            productseries,
            distribution,
            distroseries,
            sourcepackagename,
            viewed_by,
            tag,
            status,
            milestone,
            importance,
            has_patch,
            fixed_upstream,
            access_policy
        FROM BugSummaryJournal
        WHERE id <= max_id
        GROUP BY
            product, productseries, distribution, distroseries,
            sourcepackagename, viewed_by, tag, status, milestone,
            importance, has_patch, fixed_upstream, access_policy
        HAVING sum(count) <> 0
    LOOP
        IF d.count < 0 THEN
            PERFORM bug_summary_dec(d);
        ELSIF d.count > 0 THEN
            PERFORM bug_summary_inc(d);
        END IF;
    END LOOP;

    -- Clean out any counts we reduced to 0.
    DELETE FROM BugSummary WHERE count=0;
    -- Clean out the journal entries we have handled.
    DELETE FROM BugSummaryJournal WHERE id <= max_id;
END;
$function$;


CREATE OR REPLACE FUNCTION public.bug_summary_inc(d bugsummary)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Shameless adaption from postgresql manual
    LOOP
        -- first try to update the row
        UPDATE BugSummary SET count = count + d.count
        WHERE
            ((product IS NULL AND $1.product IS NULL)
                OR product = $1.product)
            AND ((productseries IS NULL AND $1.productseries IS NULL)
                OR productseries = $1.productseries)
            AND ((distribution IS NULL AND $1.distribution IS NULL)
                OR distribution = $1.distribution)
            AND ((distroseries IS NULL AND $1.distroseries IS NULL)
                OR distroseries = $1.distroseries)
            AND ((sourcepackagename IS NULL AND $1.sourcepackagename IS NULL)
                OR sourcepackagename = $1.sourcepackagename)
            AND ((viewed_by IS NULL AND $1.viewed_by IS NULL)
                OR viewed_by = $1.viewed_by)
            AND ((tag IS NULL AND $1.tag IS NULL)
                OR tag = $1.tag)
            AND status = $1.status
            AND ((milestone IS NULL AND $1.milestone IS NULL)
                OR milestone = $1.milestone)
            AND importance = $1.importance
            AND has_patch = $1.has_patch
            AND fixed_upstream = $1.fixed_upstream
            AND access_policy IS NOT DISTINCT FROM $1.access_policy;
        IF found THEN
            RETURN;
        END IF;
        -- not there, so try to insert the key
        -- if someone else inserts the same key concurrently,
        -- we could get a unique-key failure
        BEGIN
            INSERT INTO BugSummary(
                count, product, productseries, distribution,
                distroseries, sourcepackagename, viewed_by, tag,
                status, milestone, importance, has_patch, fixed_upstream,
                access_policy)
            VALUES (
                d.count, d.product, d.productseries, d.distribution,
                d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
                d.status, d.milestone, d.importance, d.has_patch,
                d.fixed_upstream, d.access_policy);
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- do nothing, and loop to try the UPDATE again
        END;
    END LOOP;
END;
$function$;

CREATE OR REPLACE FUNCTION public.bug_summary_dec(bugsummary)
 RETURNS void
 LANGUAGE sql
AS $function$
    -- We own the row reference, so in the absence of bugs this cannot
    -- fail - just decrement the row.
    UPDATE BugSummary SET count = count + $1.count
    WHERE
        ((product IS NULL AND $1.product IS NULL)
            OR product = $1.product)
        AND ((productseries IS NULL AND $1.productseries IS NULL)
            OR productseries = $1.productseries)
        AND ((distribution IS NULL AND $1.distribution IS NULL)
            OR distribution = $1.distribution)
        AND ((distroseries IS NULL AND $1.distroseries IS NULL)
            OR distroseries = $1.distroseries)
        AND ((sourcepackagename IS NULL AND $1.sourcepackagename IS NULL)
            OR sourcepackagename = $1.sourcepackagename)
        AND ((viewed_by IS NULL AND $1.viewed_by IS NULL)
            OR viewed_by = $1.viewed_by)
        AND ((tag IS NULL AND $1.tag IS NULL)
            OR tag = $1.tag)
        AND status = $1.status
        AND ((milestone IS NULL AND $1.milestone IS NULL)
            OR milestone = $1.milestone)
        AND importance = $1.importance
        AND has_patch = $1.has_patch
        AND fixed_upstream = $1.fixed_upstream
        AND access_policy IS NOT DISTINCT FROM access_policy;
$function$;

DROP VIEW combinedbugsummary;
CREATE OR REPLACE VIEW combinedbugsummary AS
    SELECT
        bugsummary.id, bugsummary.count, bugsummary.product,
        bugsummary.productseries, bugsummary.distribution,
        bugsummary.distroseries, bugsummary.sourcepackagename,
        bugsummary.viewed_by, bugsummary.tag, bugsummary.status,
        bugsummary.milestone, bugsummary.importance, bugsummary.has_patch,
        bugsummary.fixed_upstream, bugsummary.access_policy
    FROM bugsummary
    UNION ALL 
    SELECT
        -bugsummaryjournal.id AS id, bugsummaryjournal.count,
        bugsummaryjournal.product, bugsummaryjournal.productseries,
        bugsummaryjournal.distribution, bugsummaryjournal.distroseries,
        bugsummaryjournal.sourcepackagename, bugsummaryjournal.viewed_by,
        bugsummaryjournal.tag, bugsummaryjournal.status,
        bugsummaryjournal.milestone, bugsummaryjournal.importance,
        bugsummaryjournal.has_patch, bugsummaryjournal.fixed_upstream,
        bugsummaryjournal.access_policy
    FROM bugsummaryjournal;

-- With BugSummary updates now triggered by BugTaskFlat we can do away
-- with the triggers on the tables it aggregates. Only BugTaskFlat and
-- BugTag remain.
DROP TRIGGER bug_maintain_bug_summary_trigger ON bug;
DROP TRIGGER bugtask_maintain_bug_summary_before_trigger ON bugtask;
DROP TRIGGER bugtask_maintain_bug_summary_after_trigger ON bugtask;
DROP TRIGGER bugsubscription_maintain_bug_summary_before_trigger ON bugsubscription;
DROP TRIGGER bugsubscription_maintain_bug_summary_after_trigger ON bugsubscription;
DROP FUNCTION bug_maintain_bug_summary();
DROP FUNCTION bugtask_maintain_bug_summary();
DROP FUNCTION bugsubscription_maintain_bug_summary();

CREATE TRIGGER bugtaskflat_maintain_bug_summary
    AFTER INSERT OR UPDATE OR DELETE ON bugtaskflat
    FOR EACH ROW EXECUTE PROCEDURE bugtaskflat_maintain_bug_summary();


-- Dispose of various other unused functions.
DROP FUNCTION unsummarise_bug(bug);
DROP FUNCTION summarise_bug(bug);
DROP FUNCTION bug_summary_temp_journal_ins(bugsummary);
DROP FUNCTION bugsummary_journal_ins(bugsummary);
DROP FUNCTION bugsummary_locations(bug);
DROP FUNCTION bugsummary_tags(bug);
DROP FUNCTION bugsummary_tasks(bug);
DROP FUNCTION bugsummary_viewers(bug);

-- Remove foreign key constraints. This table is generated from a set of
-- constrained columns, so the constraints here serve only to make
-- things slower.
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_distribution_fkey;
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_distroseries_fkey;
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_milestone_fkey;
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_product_fkey;
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_productseries_fkey;
ALTER TABLE bugsummaryjournal DROP CONSTRAINT bugsummaryjournal_sourcepackagename_fkey;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 19, 0);
