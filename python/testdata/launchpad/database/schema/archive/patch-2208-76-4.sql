-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

DROP FUNCTION bugsummary_rollup_journal();

CREATE OR REPLACE FUNCTION bugsummary_rollup_journal(batchsize integer=NULL)
RETURNS VOID
LANGUAGE plpgsql VOLATILE
CALLED ON NULL INPUT
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
            fixed_upstream
        FROM BugSummaryJournal
        WHERE id <= max_id
        GROUP BY
            product, productseries, distribution, distroseries,
            sourcepackagename, viewed_by, tag, status, milestone,
            importance, has_patch, fixed_upstream
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
$$;

COMMENT ON FUNCTION bugsummary_rollup_journal(integer) IS
'Collate and migrate rows from BugSummaryJournal to BugSummary';


CREATE OR REPLACE FUNCTION bug_summary_dec(bugsummary) RETURNS VOID
LANGUAGE SQL AS
$$
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
        AND fixed_upstream = $1.fixed_upstream;
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
            AND fixed_upstream = $1.fixed_upstream;
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
                status, milestone,
                importance, has_patch, fixed_upstream)
            VALUES (
                d.count, d.product, d.productseries, d.distribution,
                d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
                d.status, d.milestone,
                d.importance, d.has_patch, d.fixed_upstream);
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- do nothing, and loop to try the UPDATE again
        END;
    END LOOP;
END;
$$;



INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 76, 4);
