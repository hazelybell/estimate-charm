-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Trash our existing data, which we will rebuild in a minute.
-- Slony-I doesn't like TRUNCATE noramlly, but OK in a DB patch.
TRUNCATE BugSummary;
TRUNCATE BugSummaryJournal;

-- Drop indexes we will rebuild later.
DROP INDEX bugsummary__dimensions__unique;
DROP INDEX bugsummary__full__idx;

ALTER TABLE BugSummary
    -- Add a missing foreign key constraint we were unable to add live.
    -- Person table is always being read, so locks are never acquired.
    ADD CONSTRAINT bugsummaryjournal_viewed_by_fkey
        FOREIGN KEY(viewed_by) REFERENCES Person ON DELETE CASCADE,
    ADD COLUMN importance integer NOT NULL,
    ADD COLUMN has_patch boolean NOT NULL,
    ADD COLUMN fixed_upstream boolean NOT NULL;

ALTER TABLE BugSummaryJournal
    ADD COLUMN importance integer NOT NULL,
    ADD COLUMN has_patch boolean NOT NULL,
    ADD COLUMN fixed_upstream boolean NOT NULL;

DROP VIEW CombinedBugSummary;
CREATE VIEW CombinedBugSummary AS (
    SELECT
        id, count, product, productseries, distribution, distroseries,
        sourcepackagename, viewed_by, tag, status, milestone,
        importance, has_patch, fixed_upstream
    FROM BugSummary
    UNION ALL
    SELECT
        -id as id, count, product, productseries, distribution, distroseries,
        sourcepackagename, viewed_by, tag, status, milestone,
        importance, has_patch, fixed_upstream
    FROM BugSummaryJournal);


-- Rebuild the BugSummary data with the new columns.
INSERT INTO BugSummary (
    count, product, productseries, distribution, distroseries,
    sourcepackagename, viewed_by, tag, status, importance, has_patch,
    fixed_upstream, milestone)
WITH
    -- kill dupes
    relevant_bug AS (SELECT * FROM bug where duplicateof is NULL),

    -- (bug.id, tag) for all bug-tag pairs plus (bug.id, NULL) for all bugs
    bug_tags AS (
        SELECT relevant_bug.id, NULL::text AS tag FROM relevant_bug
        UNION
        SELECT relevant_bug.id, tag
        FROM relevant_bug INNER JOIN bugtag ON relevant_bug.id=bugtag.bug),

    -- (bug.id, NULL) for all public bugs + (bug.id, viewer) for all
    -- (subscribers+assignee) on private bugs
    bug_viewers AS (
        SELECT relevant_bug.id, NULL::integer AS person
        FROM relevant_bug WHERE NOT relevant_bug.private
        UNION
        SELECT relevant_bug.id, assignee AS person
        FROM relevant_bug
        INNER JOIN bugtask ON relevant_bug.id=bugtask.bug
        WHERE relevant_bug.private and bugtask.assignee IS NOT NULL
        UNION
        SELECT relevant_bug.id, bugsubscription.person
        FROM relevant_bug INNER JOIN bugsubscription
            ON bugsubscription.bug=relevant_bug.id WHERE relevant_bug.private),

    -- (bugtask.(bug, product, productseries, distribution, distroseries,
    -- sourcepackagename, status, milestone) for all bugs + the same with
    -- sourcepackage squashed to NULL)
    tasks AS (
        SELECT
            bug, product, productseries, distribution, distroseries,
            sourcepackagename, status, importance,
            (EXISTS
                (SELECT TRUE
                FROM BugTask AS RelatedBugTask
                WHERE RelatedBugTask.bug = BugTask.bug
                AND RelatedBugTask.id != BugTask.id
                AND ((RelatedBugTask.bugwatch IS NOT NULL
                        AND RelatedBugTask.status IN (17, 25, 30))
                        OR (RelatedBugTask.product IS NOT NULL
                            AND RelatedBugTask.bugwatch IS NULL
                            AND RelatedBugTask.status IN (25, 30))))
                ) as fixed_upstream, milestone
        FROM bugtask
        UNION
        SELECT DISTINCT ON (
            bug, product, productseries, distribution, distroseries,
            sourcepackagename, milestone)
            bug, product, productseries, distribution, distroseries,
            NULL::integer as sourcepackagename,
            status, importance,
            (EXISTS
                (SELECT TRUE
                FROM BugTask AS RelatedBugTask
                WHERE RelatedBugTask.bug = BugTask.bug
                AND RelatedBugTask.id != BugTask.id
                AND ((RelatedBugTask.bugwatch IS NOT NULL
                        AND RelatedBugTask.status IN (17, 25, 30))
                        OR (RelatedBugTask.product IS NOT NULL
                            AND RelatedBugTask.bugwatch IS NULL
                            AND RelatedBugTask.status IN (25, 30))))
                ) as fixed_upstream, milestone
        FROM bugtask where sourcepackagename IS NOT NULL)

    -- Now combine
    SELECT
        count(*), product, productseries, distribution, distroseries,
        sourcepackagename, person, tag, status, importance,
        latest_patch_uploaded IS NOT NULL AS has_patch, fixed_upstream,
        milestone
    FROM relevant_bug
    INNER JOIN bug_tags ON relevant_bug.id=bug_tags.id
    INNER JOIN bug_viewers ON relevant_bug.id=bug_viewers.id
    INNER JOIN tasks on tasks.bug=relevant_bug.id
    GROUP BY
        product, productseries, distribution, distroseries,
        sourcepackagename, person, tag, status, importance, has_patch,
        fixed_upstream, milestone;


-- Rebuild indexes.
CREATE INDEX bugsummary__full__idx ON BugSummary (
    tag, status, product, productseries, distribution,
    distroseries, sourcepackagename, viewed_by, milestone,
    importance, has_patch, fixed_upstream);
-- Enforce uniqueness again.
CREATE UNIQUE INDEX bugsummary__product__unique
    ON BugSummary(
        product, status, importance, has_patch, fixed_upstream,
        COALESCE(tag, ''), COALESCE(milestone, -1), COALESCE(viewed_by, -1))
    WHERE product IS NOT NULL;
CREATE UNIQUE INDEX bugsummary__productseries__unique
    ON BugSummary(
        productseries, status, importance, has_patch, fixed_upstream,
        COALESCE(tag, ''), COALESCE(milestone, -1), COALESCE(viewed_by, -1))
    WHERE productseries IS NOT NULL;
CREATE UNIQUE INDEX bugsummary__distribution__unique
    ON BugSummary(
        distribution, status, importance, has_patch, fixed_upstream,
        COALESCE(sourcepackagename, -1),
        COALESCE(tag, ''), COALESCE(milestone, -1), COALESCE(viewed_by, -1))
    WHERE distribution IS NOT NULL;
CREATE UNIQUE INDEX bugsummary__distroseries__unique
    ON BugSummary(
        distroseries, status, importance, has_patch, fixed_upstream,
        COALESCE(sourcepackagename, -1),
        COALESCE(tag, ''), COALESCE(milestone, -1), COALESCE(viewed_by, -1))
    WHERE distroseries IS NOT NULL;


-- Rebuild relevant trigger functions.
CREATE OR REPLACE FUNCTION bugsummary_journal_ins(d bugsummary)
RETURNS VOID
LANGUAGE plpgsql AS
$$
BEGIN
    IF d.count <> 0 THEN
        INSERT INTO BugSummaryJournal (
            count, product, productseries, distribution,
            distroseries, sourcepackagename, viewed_by, tag,
            status, milestone,
            importance, has_patch, fixed_upstream)
        VALUES (
            d.count, d.product, d.productseries, d.distribution,
            d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
            d.status, d.milestone,
            d.importance, d.has_patch, d.fixed_upstream);
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
        AND milestone IS NOT DISTINCT FROM $1.milestone
        AND importance IS NOT DISTINCT FROM $1.importance
        AND has_patch IS NOT DISTINCT FROM $1.has_patch
        AND fixed_upstream IS NOT DISTINCT FROM $1.fixed_upstream;
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
        AND milestone IS NOT DISTINCT FROM $1.milestone
        AND importance IS NOT DISTINCT FROM $1.importance
        AND has_patch IS NOT DISTINCT FROM $1.has_patch
        AND fixed_upstream IS NOT DISTINCT FROM $1.fixed_upstream;
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
            AND milestone IS NOT DISTINCT FROM d.milestone
            AND importance IS NOT DISTINCT FROM d.importance
            AND has_patch IS NOT DISTINCT FROM d.has_patch
            AND fixed_upstream IS NOT DISTINCT FROM d.fixed_upstream;
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

COMMENT ON FUNCTION bugsummary_rollup_journal() IS
'Collate and migrate rows from BugSummaryJournal to BugSummary';


CREATE OR REPLACE FUNCTION ensure_bugsummary_temp_journal() RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
BEGIN
    CREATE TEMPORARY TABLE bugsummary_temp_journal (
        LIKE bugsummary ) ON COMMIT DROP;
    ALTER TABLE bugsummary_temp_journal ALTER COLUMN id DROP NOT NULL;
EXCEPTION
    WHEN duplicate_table THEN
        NULL;
END;
$$;

COMMENT ON FUNCTION ensure_bugsummary_temp_journal() IS
'Create a temporary table bugsummary_temp_journal if it does not exist.';


CREATE OR REPLACE FUNCTION bug_summary_temp_journal_ins(d bugsummary)
RETURNS VOID LANGUAGE plpgsql AS
$$
BEGIN
    INSERT INTO BugSummary_Temp_Journal(
        count, product, productseries, distribution,
        distroseries, sourcepackagename, viewed_by, tag,
        status, milestone, importance, has_patch, fixed_upstream)
    VALUES (
        d.count, d.product, d.productseries, d.distribution,
        d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
        d.status, d.milestone, d.importance, d.has_patch, d.fixed_upstream);
    RETURN;
END;
$$;

COMMENT ON FUNCTION bug_summary_temp_journal_ins(bugsummary) IS
'Insert a BugSummary into the temporary journal';


-- Don't need these. Faster to just append rows to the journal
-- than attempt to update existing rows.
DROP FUNCTION bug_summary_temp_journal_dec(bugsummary);
DROP FUNCTION bug_summary_temp_journal_inc(bugsummary);


CREATE OR REPLACE FUNCTION bug_summary_flush_temp_journal() RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- may get called even though no summaries were made (for simplicity in the
    -- callers)
    PERFORM ensure_bugsummary_temp_journal();
    FOR d IN 
        SELECT
            NULL::integer AS id, SUM(count), product, productseries,
            distribution, distroseries, sourcepackagename,
            viewed_by, tag, status, milestone,
            importance, has_patch, fixed_upstream
        FROM BugSummary_temp_journal
        GROUP BY
            product, productseries,
            distribution, distroseries, sourcepackagename,
            viewed_by, tag, status, milestone, importance,
            has_patch, fixed_upstream
        HAVING SUM(count) <> 0
    LOOP
        IF d.count < 0 THEN
            PERFORM bug_summary_dec(d);
        ELSE
            PERFORM bug_summary_inc(d);
        END IF;
    END LOOP;
    TRUNCATE bugsummary_temp_journal;
END;
$$;

COMMENT ON FUNCTION bug_summary_flush_temp_journal() IS
'flush the temporary bugsummary journal into the bugsummary table';


CREATE OR REPLACE FUNCTION unsummarise_bug(BUG_ROW bug) RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    PERFORM ensure_bugsummary_temp_journal();
    FOR d IN SELECT * FROM bugsummary_locations(BUG_ROW) LOOP
        d.count = -1;
        PERFORM bug_summary_temp_journal_ins(d);
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION summarise_bug(BUG_ROW bug) RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    PERFORM ensure_bugsummary_temp_journal();
    FOR d IN SELECT * FROM bugsummary_locations(BUG_ROW) LOOP
        d.count = 1;
        PERFORM bug_summary_temp_journal_ins(d);
    END LOOP;
END;
$$;


CREATE OR REPLACE FUNCTION bug_maintain_bug_summary() RETURNS TRIGGER
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path TO public AS
$$
BEGIN
    -- There is no INSERT logic, as a bug will not have any summary
    -- information until BugTask rows have been attached.
    IF TG_OP = 'UPDATE' THEN
        IF OLD.duplicateof IS DISTINCT FROM NEW.duplicateof
            OR OLD.private IS DISTINCT FROM NEW.private
            OR (OLD.latest_patch_uploaded IS NULL)
                <> (NEW.latest_patch_uploaded IS NULL) THEN
            PERFORM unsummarise_bug(OLD);
            PERFORM summarise_bug(NEW);
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        PERFORM unsummarise_bug(OLD);
    END IF;

    PERFORM bug_summary_flush_temp_journal();
    RETURN NULL; -- Ignored - this is an AFTER trigger
END;
$$;


CREATE OR REPLACE FUNCTION bugtask_maintain_bug_summary() RETURNS TRIGGER
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path TO public AS
$$
BEGIN
    -- This trigger only works if we are inserting, updating or deleting
    -- a single row per statement.

    -- Unlike bug_maintain_bug_summary, this trigger does not have access
    -- to the old bug when invoked as an AFTER trigger. To work around this
    -- we install this trigger as both a BEFORE and an AFTER trigger.
    IF TG_OP = 'INSERT' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(NEW.bug));
        ELSE
            PERFORM summarise_bug(bug_row(NEW.bug));
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(OLD.bug));
        ELSE
            PERFORM summarise_bug(bug_row(OLD.bug));
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN OLD;

    ELSE
        IF (OLD.product IS DISTINCT FROM NEW.product
            OR OLD.productseries IS DISTINCT FROM NEW.productseries
            OR OLD.distribution IS DISTINCT FROM NEW.distribution
            OR OLD.distroseries IS DISTINCT FROM NEW.distroseries
            OR OLD.sourcepackagename IS DISTINCT FROM NEW.sourcepackagename
            OR OLD.status IS DISTINCT FROM NEW.status
            OR OLD.importance IS DISTINCT FROM NEW.importance
            OR OLD.bugwatch IS DISTINCT FROM NEW.bugwatch
            OR OLD.milestone IS DISTINCT FROM NEW.milestone) THEN

            IF TG_WHEN = 'BEFORE' THEN
                PERFORM unsummarise_bug(bug_row(OLD.bug));
                IF OLD.bug <> NEW.bug THEN
                    PERFORM unsummarise_bug(bug_row(NEW.bug));
                END IF;
            ELSE
                PERFORM summarise_bug(bug_row(OLD.bug));
                IF OLD.bug <> NEW.bug THEN
                    PERFORM summarise_bug(bug_row(NEW.bug));
                END IF;
            END IF;
        END IF;
        PERFORM bug_summary_flush_temp_journal();
        RETURN NEW;
    END IF;
END;
$$;


CREATE OR REPLACE FUNCTION bugsummary_locations(BUG_ROW bug)
RETURNS SETOF bugsummary LANGUAGE plpgsql AS
$$
BEGIN
    IF BUG_ROW.duplicateof IS NOT NULL THEN
        RETURN;
    END IF;
    RETURN QUERY
        SELECT
            CAST(NULL AS integer) AS id,
            CAST(1 AS integer) AS count,
            product, productseries, distribution, distroseries,
            sourcepackagename, person AS viewed_by, tag, status, milestone,
            importance,
            BUG_ROW.latest_patch_uploaded IS NOT NULL AS has_patch,
            (EXISTS (
                SELECT TRUE FROM BugTask AS RBT
                WHERE
                    RBT.bug = tasks.bug
                    -- This would just be 'RBT.id <> tasks.id', except
                    -- that the records from tasks are summaries and not
                    -- real bugtasks, and do not have an id.
                    AND (RBT.product IS DISTINCT FROM tasks.product
                        OR RBT.productseries
                            IS DISTINCT FROM tasks.productseries
                        OR RBT.distribution IS DISTINCT FROM tasks.distribution
                        OR RBT.distroseries IS DISTINCT FROM tasks.distroseries
                        OR RBT.sourcepackagename
                            IS DISTINCT FROM tasks.sourcepackagename)
                    -- Flagged as INVALID, FIXCOMMITTED or FIXRELEASED
                    -- via a bugwatch, or FIXCOMMITTED or FIXRELEASED on
                    -- the product.
                    AND ((bugwatch IS NOT NULL AND status IN (17, 25, 30))
                        OR (bugwatch IS NULL AND product IS NOT NULL
                            AND status IN (25, 30))))
                )::boolean AS fixed_upstream
        FROM bugsummary_tasks(BUG_ROW) AS tasks
        JOIN bugsummary_tags(BUG_ROW) AS bug_tags ON TRUE
        LEFT OUTER JOIN bugsummary_viewers(BUG_ROW) AS bug_viewers ON TRUE;
END;
$$;

COMMENT ON FUNCTION bugsummary_locations(bug) IS
'Calculate what BugSummary rows should exist for a given Bug.';


CREATE OR REPLACE FUNCTION bugsummary_tasks(BUG_ROW bug)
RETURNS SETOF bugtask LANGUAGE plpgsql STABLE AS
$$
DECLARE
    bt bugtask%ROWTYPE;
    r record;
BEGIN
    bt.bug = BUG_ROW.id;

    -- One row only for each target permutation - need to ignore other fields
    -- like date last modified to deal with conjoined masters and multiple
    -- sourcepackage tasks in a distro.
    FOR r IN
        SELECT
            product, productseries, distribution, distroseries,
            sourcepackagename, status, milestone, importance, bugwatch
        FROM BugTask WHERE bug=BUG_ROW.id
        UNION -- Implicit DISTINCT
        SELECT
            product, productseries, distribution, distroseries,
            NULL, status, milestone, importance, bugwatch
        FROM BugTask WHERE bug=BUG_ROW.id AND sourcepackagename IS NOT NULL
    LOOP
        bt.product = r.product;
        bt.productseries = r.productseries;
        bt.distribution = r.distribution;
        bt.distroseries = r.distroseries;
        bt.sourcepackagename = r.sourcepackagename;
        bt.status = r.status;
        bt.milestone = r.milestone;
        bt.importance = r.importance;
        bt.bugwatch = r.bugwatch;
        RETURN NEXT bt;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION bugsummary_tasks(bug) IS
'Return all tasks for the bug + all sourcepackagename tasks again with the sourcepackagename squashed';



INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 75, 0);
