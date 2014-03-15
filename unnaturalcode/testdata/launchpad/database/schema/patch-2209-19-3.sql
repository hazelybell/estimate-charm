-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

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
        status, milestone, importance, has_patch, access_policy)
    SELECT
        SUM(count), product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, access_policy
    FROM bugsummary_temp_journal
    GROUP BY
        product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, access_policy
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
        status, milestone, importance, has_patch, access_policy)
    SELECT
        _count, product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, access_policy
        FROM bugsummary_locations(btf_row);
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
            bug_viewers.access_policy
        FROM
            bugsummary_targets(btf_row) as bug_targets,
            bugsummary_tags(btf_row) AS bug_tags,
            bugsummary_viewers(btf_row) AS bug_viewers;
END;
$function$;

-- Changing the return type requires a DROP + CREATE.
DROP FUNCTION public.bugsummary_viewers(btf_row bugtaskflat);
CREATE FUNCTION public.bugsummary_viewers(btf_row bugtaskflat)
 RETURNS TABLE(viewed_by integer, access_policy integer)
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT NULL::integer, NULL::integer WHERE $1.information_type IN (1, 2)
    UNION ALL
    SELECT unnest($1.access_grants), NULL::integer
    WHERE $1.information_type IN (3, 4, 5)
    UNION ALL
    SELECT NULL::integer, unnest($1.access_policies)
    WHERE $1.information_type IN (3, 4, 5);
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
        OR NEW.duplicateof IS DISTINCT FROM OLD.duplicateof
    THEN
        PERFORM bugsummary_journal_bugtaskflat(OLD, -1);
        PERFORM bugsummary_journal_bugtaskflat(NEW, 1);
        PERFORM bug_summary_flush_temp_journal();
    END IF;
    RETURN NULL;
END;
$function$;

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
            access_policy
        FROM BugSummaryJournal
        WHERE id <= max_id
        GROUP BY
            product, productseries, distribution, distroseries,
            sourcepackagename, viewed_by, tag, status, milestone,
            importance, has_patch, access_policy
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
                status, milestone, importance, has_patch, access_policy)
            VALUES (
                d.count, d.product, d.productseries, d.distribution,
                d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
                d.status, d.milestone, d.importance, d.has_patch,
                d.access_policy);
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
        bugsummary.access_policy
    FROM bugsummary
    UNION ALL 
    SELECT
        -bugsummaryjournal.id AS id, bugsummaryjournal.count,
        bugsummaryjournal.product, bugsummaryjournal.productseries,
        bugsummaryjournal.distribution, bugsummaryjournal.distroseries,
        bugsummaryjournal.sourcepackagename, bugsummaryjournal.viewed_by,
        bugsummaryjournal.tag, bugsummaryjournal.status,
        bugsummaryjournal.milestone, bugsummaryjournal.importance,
        bugsummaryjournal.has_patch, bugsummaryjournal.access_policy
    FROM bugsummaryjournal;

DROP INDEX bugsummary__distribution__unique;
DROP INDEX bugsummary__distroseries__unique;
DROP INDEX bugsummary__product__unique;
DROP INDEX bugsummary__productseries__unique;
DROP INDEX bugsummary__distribution__idx;
DROP INDEX bugsummary__distroseries__idx;
DROP INDEX bugsummary__full__idx;
DROP INDEX bugsummary__distribution_count__idx;
DROP INDEX bugsummary__distribution_tag_count__idx;
DROP INDEX bugsummary__tag_count__idx;
ALTER INDEX bugsummary__distribution__idx2 RENAME TO bugsummary__distribution__idx;
ALTER INDEX bugsummary__distroseries__idx2 RENAME TO bugsummary__distroseries__idx;
ALTER INDEX bugsummary__distribution_count__idx2 RENAME TO bugsummary__distribution_count__idx;
ALTER INDEX bugsummary__distroseries_count__idx2 RENAME TO bugsummary__distroseries_count__idx;
ALTER INDEX bugsummary__distribution_tag_count__idx2 RENAME TO bugsummary__distribution_tag_count__idx;
ALTER INDEX bugsummary__distroseries_tag_count__idx2 RENAME TO bugsummary__distroseries_tag_count__idx;
ALTER INDEX bugsummary__full__idx2 RENAME TO bugsummary__full__idx;

ALTER TABLE bugsummary DROP COLUMN fixed_upstream;
ALTER TABLE bugsummaryjournal DROP COLUMN fixed_upstream;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 19, 3);
