-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION bugsummary_journal_ins(d bugsummary)
RETURNS VOID
LANGUAGE plpgsql AS
$$
BEGIN
    IF d.count <> 0 THEN
        INSERT INTO BugSummaryJournal (
            count, product, productseries, distribution,
            distroseries, sourcepackagename, viewed_by, tag,
            status, milestone)
        VALUES (
            d.count, d.product, d.productseries, d.distribution,
            d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
            d.status, d.milestone);
    END IF;
END;
$$;

COMMENT ON FUNCTION bugsummary_journal_ins(bugsummary) IS
'Add an entry into BugSummaryJournal';


CREATE OR REPLACE FUNCTION bugsummary_rollup_journal() RETURNS VOID
LANGUAGE plpgsql VOLATILE
SECURITY DEFINER SET search_path TO public AS
$$
DECLARE
    d bugsummary%ROWTYPE;
    max_id integer;
BEGIN
    -- Lock so we don't content with other invokations of this
    -- function. We can happily lock the BugSummary table for writes
    -- as this function is the only thing that updates that table.
    -- BugSummaryJournal remains unlocked so nothing should be blocked.
    LOCK TABLE BugSummary IN ROW EXCLUSIVE MODE;

    SELECT MAX(id) INTO max_id FROM BugSummaryJournal;

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
            milestone
        FROM BugSummaryJournal
        WHERE id <= max_id
        GROUP BY
            product, productseries, distribution, distroseries,
            sourcepackagename, viewed_by, tag, status, milestone
        HAVING sum(count) <> 0
    LOOP
        IF d.count < 0 THEN
            PERFORM bug_summary_dec(d);
        ELSIF d.count > 0 THEN
            PERFORM bug_summary_inc(d);
        END IF;
    END LOOP;

    DELETE FROM BugSummaryJournal WHERE id <= max_id;
END;
$$;

CREATE OR REPLACE FUNCTION bug_summary_dec(bugsummary) RETURNS VOID
LANGUAGE SQL AS
$$
    -- We own the row reference, so in the absence of bugs this cannot
    -- fail - just decrement the row.
    UPDATE BugSummary SET count = count + $1.count
    WHERE
        product IS NOT DISTINCT FROM $1.product
        AND productseries IS NOT DISTINCT FROM $1.productseries
        AND distribution IS NOT DISTINCT FROM $1.distribution
        AND distroseries IS NOT DISTINCT FROM $1.distroseries
        AND sourcepackagename IS NOT DISTINCT FROM $1.sourcepackagename
        AND viewed_by IS NOT DISTINCT FROM $1.viewed_by
        AND tag IS NOT DISTINCT FROM $1.tag
        AND status IS NOT DISTINCT FROM $1.status
        AND milestone IS NOT DISTINCT FROM $1.milestone;
    -- gc the row (perhaps should be garbo but easy enough to add here:
    DELETE FROM bugsummary
    WHERE
        count=0
        AND product IS NOT DISTINCT FROM $1.product
        AND productseries IS NOT DISTINCT FROM $1.productseries
        AND distribution IS NOT DISTINCT FROM $1.distribution
        AND distroseries IS NOT DISTINCT FROM $1.distroseries
        AND sourcepackagename IS NOT DISTINCT FROM $1.sourcepackagename
        AND viewed_by IS NOT DISTINCT FROM $1.viewed_by
        AND tag IS NOT DISTINCT FROM $1.tag
        AND status IS NOT DISTINCT FROM $1.status
        AND milestone IS NOT DISTINCT FROM $1.milestone;
    -- If its not found then someone else also dec'd and won concurrently.
$$;

CREATE OR REPLACE FUNCTION bug_summary_inc(d bugsummary) RETURNS VOID
LANGUAGE plpgsql AS
$$
BEGIN
    -- Shameless adaption from postgresql manual
    LOOP
        -- first try to update the row
        UPDATE BugSummary SET count = count + d.count
        WHERE
            product IS NOT DISTINCT FROM d.product
            AND productseries IS NOT DISTINCT FROM d.productseries
            AND distribution IS NOT DISTINCT FROM d.distribution
            AND distroseries IS NOT DISTINCT FROM d.distroseries
            AND sourcepackagename IS NOT DISTINCT FROM d.sourcepackagename
            AND viewed_by IS NOT DISTINCT FROM d.viewed_by
            AND tag IS NOT DISTINCT FROM d.tag
            AND status IS NOT DISTINCT FROM d.status
            AND milestone IS NOT DISTINCT FROM d.milestone;
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
                status, milestone)
            VALUES (
                d.count, d.product, d.productseries, d.distribution,
                d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
                d.status, d.milestone);
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- do nothing, and loop to try the UPDATE again
        END;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION bugsummary_rollup_journal() IS
'Collate and migrate rows from BugSummaryJournal to BugSummary';

CREATE OR REPLACE FUNCTION bug_summary_flush_temp_journal() RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- may get called even though no summaries were made (for simplicity in the
    -- callers)
    PERFORM ensure_bugsummary_temp_journal();
    FOR d IN SELECT * FROM bugsummary_temp_journal LOOP
        PERFORM bugsummary_journal_ins(d);
    END LOOP;
    TRUNCATE bugsummary_temp_journal;
END;
$$;

COMMENT ON FUNCTION bug_summary_flush_temp_journal() IS
'flush the temporary bugsummary journal into the bugsummaryjournal table';


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 63, 4);
