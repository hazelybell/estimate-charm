-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE BugSummary(
    -- Slony needs a primary key and there are no natural candidates.
    id serial PRIMARY KEY,
    count INTEGER NOT NULL default 0,
    product INTEGER REFERENCES Product ON DELETE CASCADE,
    productseries INTEGER REFERENCES ProductSeries ON DELETE CASCADE,
    distribution INTEGER REFERENCES Distribution ON DELETE CASCADE,
    distroseries INTEGER REFERENCES DistroSeries ON DELETE CASCADE,
    sourcepackagename INTEGER REFERENCES SourcePackageName ON DELETE CASCADE,
    viewed_by INTEGER, -- No REFERENCES because it is trigger maintained.
    tag TEXT,
    status INTEGER NOT NULL,
    milestone INTEGER REFERENCES Milestone ON DELETE CASCADE,
    CONSTRAINT bugtask_assignment_checks CHECK (
        CASE
            WHEN product IS NOT NULL THEN
                productseries IS NULL
                AND distribution IS NULL
                AND distroseries IS NULL
                AND sourcepackagename IS NULL
            WHEN productseries IS NOT NULL THEN
                distribution IS NULL
                AND distroseries IS NULL
                AND sourcepackagename IS NULL
            WHEN distribution IS NOT NULL THEN
                distroseries IS NULL
            WHEN distroseries IS NOT NULL THEN
                TRUE
            ELSE
                FALSE
        END)
);

---- Bulk load into the table - after this it is maintained by trigger. Timed
-- at 2-3 minutes on staging.
-- basic theory: each bug *task* has some unary dimensions (like status) and
-- some N-ary dimensions (like contexts [sourcepackage+distro, distro only], or
-- subscriptions, or tags). For N-ary dimensions we record the bug against all
-- positions in that dimension.
-- Some tasks aggregate into the same dimension - e.g. two different source
-- packages tasks in Ubuntu. At the time of writing we only want to count those
-- once ( because we have had user confusion when two tasks of the same bug are
-- both counted toward portal aggregates). So we add bug.id distinct.
-- We don't map INCOMPLETE to INCOMPLETE_WITH_RESPONSE - instead we'll let that
-- migration happen separately.
-- So the rules the code below should be implementing are:
-- once for each task in a different target
-- once for each subscription (private bugs) (left join subscribers conditionally on privacy)
-- once for each sourcepackage name + one with sourcepackagename=NULL (two queries unioned)
-- once for each tag + one with tag=NULL (two queries unioned)
-- bugs with duplicateof non null are excluded because we exclude them from all our aggregates.
INSERT INTO bugsummary (
    count, product, productseries, distribution, distroseries,
    sourcepackagename, viewed_by, tag, status, milestone)
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
            sourcepackagename, status, milestone
        FROM bugtask
        UNION
        SELECT DISTINCT ON (
            bug, product, productseries, distribution, distroseries,
            sourcepackagename, milestone)
            bug, product, productseries, distribution, distroseries,
            NULL::integer as sourcepackagename,
            status, milestone
        FROM bugtask where sourcepackagename IS NOT NULL)

    -- Now combine
    SELECT
        count(*), product, productseries, distribution, distroseries,
        sourcepackagename, person, tag, status, milestone
    FROM relevant_bug
    INNER JOIN bug_tags ON relevant_bug.id=bug_tags.id
    INNER JOIN bug_viewers ON relevant_bug.id=bug_viewers.id
    INNER JOIN tasks on tasks.bug=relevant_bug.id
    GROUP BY
        product, productseries, distribution, distroseries,
        sourcepackagename, person, tag, status, milestone;

-- Need indices for FK CASCADE DELETE to find any FK easily
CREATE INDEX bugsummary__distribution__idx ON BugSummary (distribution)
    WHERE distribution IS NOT NULL;

CREATE INDEX bugsummary__distroseries__idx ON BugSummary (distroseries)
    WHERE distroseries IS NOT NULL;

CREATE INDEX bugsummary__viewed_by__idx ON BugSummary (viewed_by)
    WHERE viewed_by IS NOT NULL;

CREATE INDEX bugsummary__product__idx ON BugSummary (product)
    WHERE product IS NOT NULL;

CREATE INDEX bugsummary__productseries__idx ON BugSummary (productseries)
    WHERE productseries IS NOT NULL;

-- can only have one fact row per set of dimensions
CREATE UNIQUE INDEX bugsummary__dimensions__unique ON bugsummary (
    status,
    COALESCE(product, (-1)),
    COALESCE(productseries, (-1)),
    COALESCE(distribution, (-1)),
    COALESCE(distroseries, (-1)),
    COALESCE(sourcepackagename, (-1)),
    COALESCE(viewed_by, (-1)),
    COALESCE(milestone, (-1)),
    COALESCE(tag, ('')));

-- While querying is tolerably fast with the base dimension indices,
-- we want snappy:
-- Distribution bug counts
CREATE INDEX bugsummary__distribution_count__idx
ON BugSummary (distribution)
WHERE sourcepackagename IS NULL AND tag IS NULL;

-- Distribution wide tag counts
CREATE INDEX bugsummary__distribution_tag_count__idx
ON BugSummary (distribution)
WHERE sourcepackagename IS NULL AND tag IS NOT NULL;

-- Everything (counts)
CREATE INDEX bugsummary__status_count__idx
ON BugSummary (status)
WHERE sourcepackagename IS NULL AND tag IS NULL;

-- Everything (tags)
CREATE INDEX bugsummary__tag_count__idx
ON BugSummary (status)
WHERE sourcepackagename IS NULL AND tag IS NOT NULL;


--
-- Functions exist here for pathalogical reasons.
--
-- They can't go in trusted.sql at the moment, because trusted.sql is
-- run against an empty database. If these functions where in there,
-- it would fail because they use BugSummary table as a useful
-- composite type.
-- I suspect we will need to leave these function definitions in here,
-- and move them to trusted.sql after the baseline SQL script contains
-- the BugSummary table definition.

-- We also considered switching from one 'trusted.sql' to two files -
-- pre_patch.sql and post_patch.sql. But that doesn't gain us much
-- as the functions need to be declared before the triggers can be
-- created. It would work, but we would still need stub 'forward
-- declarations' of the functions in here, with the functions recreated
-- with the real implementation in post_patch.sql.

CREATE OR REPLACE FUNCTION bug_summary_inc(d bugsummary) RETURNS VOID
LANGUAGE plpgsql AS
$$
BEGIN
    -- Shameless adaption from postgresql manual
    LOOP
        -- first try to update the row
        UPDATE BugSummary SET count = count + 1
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
                1, d.product, d.productseries, d.distribution,
                d.distroseries, d.sourcepackagename, d.viewed_by, d.tag,
                d.status, d.milestone);
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- do nothing, and loop to try the UPDATE again
        END;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION bug_summary_inc(bugsummary) IS
'UPSERT into bugsummary incrementing one row';

CREATE OR REPLACE FUNCTION bug_summary_dec(bugsummary) RETURNS VOID
LANGUAGE SQL AS
$$
    -- We own the row reference, so in the absence of bugs this cannot
    -- fail - just decrement the row.
    UPDATE BugSummary SET count = count - 1
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

COMMENT ON FUNCTION bug_summary_inc(bugsummary) IS
'UPSERT into bugsummary incrementing one row';


CREATE OR REPLACE FUNCTION bug_row(bug_id integer)
RETURNS bug LANGUAGE SQL STABLE AS
$$
    SELECT * FROM Bug WHERE id=$1;
$$;
COMMENT ON FUNCTION bug_row(integer) IS
'Helper for manually testing functions requiring a bug row as input. eg. SELECT * FROM bugsummary_tags(bug_row(1))';


CREATE OR REPLACE FUNCTION bugsummary_viewers(BUG_ROW bug)
RETURNS SETOF bugsubscription LANGUAGE SQL STABLE AS
$$
    SELECT *
    FROM BugSubscription
    WHERE
        bugsubscription.bug=$1.id
        AND $1.private IS TRUE;
$$;

COMMENT ON FUNCTION bugsummary_viewers(bug) IS
'Return (bug, viewer) for all viewers if private, nothing otherwise';


CREATE OR REPLACE FUNCTION bugsummary_tags(BUG_ROW bug)
RETURNS SETOF bugtag LANGUAGE SQL STABLE AS
$$
    SELECT * FROM BugTag WHERE BugTag.bug = $1.id
    UNION ALL
    SELECT NULL::integer, $1.id, NULL::text;
$$;

COMMENT ON FUNCTION bugsummary_tags(bug) IS
'Return (bug, tag) for all tags + (bug, NULL::text)';


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
            sourcepackagename, status, milestone
        FROM BugTask WHERE bug=BUG_ROW.id
        UNION
        SELECT
            product, productseries, distribution, distroseries,
            NULL, status, milestone
        FROM BugTask WHERE bug=BUG_ROW.id AND sourcepackagename IS NOT NULL
    LOOP
        bt.product = r.product;
        bt.productseries = r.productseries;
        bt.distribution = r.distribution;
        bt.distroseries = r.distroseries;
        bt.sourcepackagename = r.sourcepackagename;
        bt.status = r.status;
        bt.milestone = r.milestone;
        RETURN NEXT bt;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION bugsummary_tasks(bug) IS
'Return all tasks for the bug + all sourcepackagename tasks again with the sourcepackagename squashed';


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
            sourcepackagename, person AS viewed_by, tag, status, milestone
        FROM bugsummary_tasks(BUG_ROW) AS tasks
        JOIN bugsummary_tags(BUG_ROW) AS bug_tags ON TRUE
        LEFT OUTER JOIN bugsummary_viewers(BUG_ROW) AS bug_viewers ON TRUE;
END;
$$;

COMMENT ON FUNCTION bugsummary_locations(bug) IS
'Calculate what BugSummary rows should exist for a given Bug.';


CREATE OR REPLACE FUNCTION summarise_bug(BUG_ROW bug) RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- Grab a suitable lock before we start calculating bug summary data
    -- to avoid race conditions. This lock allows SELECT but blocks writes.
    LOCK TABLE BugSummary IN ROW EXCLUSIVE MODE;
    FOR d IN SELECT * FROM bugsummary_locations(BUG_ROW) LOOP
        PERFORM bug_summary_inc(d);
    END LOOP;
END;
$$;

COMMENT ON FUNCTION summarise_bug(bug) IS
'AFTER summarise a bug row into bugsummary.';


CREATE OR REPLACE FUNCTION unsummarise_bug(BUG_ROW bug) RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- Grab a suitable lock before we start calculating bug summary data
    -- to avoid race conditions. This lock allows SELECT but blocks writes.
    LOCK TABLE BugSummary IN ROW EXCLUSIVE MODE;
    FOR d IN SELECT * FROM bugsummary_locations(BUG_ROW) LOOP
        PERFORM bug_summary_dec(d);
    END LOOP;
END;
$$;

COMMENT ON FUNCTION unsummarise_bug(bug) IS
'AFTER unsummarise a bug row from bugsummary.';


CREATE OR REPLACE FUNCTION bug_maintain_bug_summary() RETURNS TRIGGER
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path TO public AS
$$
BEGIN
    -- There is no INSERT logic, as a bug will not have any summary
    -- information until BugTask rows have been attached.
    IF TG_OP = 'UPDATE' THEN
        IF OLD.duplicateof IS DISTINCT FROM NEW.duplicateof
            OR OLD.private IS DISTINCT FROM NEW.private THEN
            PERFORM unsummarise_bug(OLD);
            PERFORM summarise_bug(NEW);
        END IF;

    ELSIF TG_OP = 'DELETE' THEN
        PERFORM unsummarise_bug(OLD);
    END IF;

    RETURN NULL; -- Ignored - this is an AFTER trigger
END;
$$;

COMMENT ON FUNCTION bug_maintain_bug_summary() IS
'AFTER trigger on bug maintaining the bugs summaries in bugsummary.';


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
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(OLD.bug));
        ELSE
            PERFORM summarise_bug(bug_row(OLD.bug));
        END IF;
        RETURN OLD;

    ELSE
        IF (OLD.product IS DISTINCT FROM NEW.product
            OR OLD.productseries IS DISTINCT FROM NEW.productseries
            OR OLD.distribution IS DISTINCT FROM NEW.distribution
            OR OLD.distroseries IS DISTINCT FROM NEW.distroseries
            OR OLD.sourcepackagename IS DISTINCT FROM NEW.sourcepackagename
            OR OLD.status IS DISTINCT FROM NEW.status
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
        RETURN NEW;
    END IF;
END;
$$;

COMMENT ON FUNCTION bugtask_maintain_bug_summary() IS
'Both BEFORE & AFTER trigger on bugtask maintaining the bugs summaries in bugsummary.';


CREATE OR REPLACE FUNCTION bugsubscription_maintain_bug_summary()
RETURNS TRIGGER LANGUAGE plpgsql VOLATILE
SECURITY DEFINER SET search_path TO public AS
$$
BEGIN
    -- This trigger only works if we are inserting, updating or deleting
    -- a single row per statement.
    IF TG_OP = 'INSERT' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(NEW.bug));
        ELSE
            PERFORM summarise_bug(bug_row(NEW.bug));
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(OLD.bug));
        ELSE
            PERFORM summarise_bug(bug_row(OLD.bug));
        END IF;
        RETURN OLD;
    ELSE
        IF (OLD.person IS DISTINCT FROM NEW.person
            OR OLD.bug IS DISTINCT FROM NEW.bug) THEN
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
        RETURN NEW;
    END IF;
END;
$$;

COMMENT ON FUNCTION bugsubscription_maintain_bug_summary() IS
'AFTER trigger on bugsubscription maintaining the bugs summaries in bugsummary.';


CREATE OR REPLACE FUNCTION bugtag_maintain_bug_summary() RETURNS TRIGGER
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path TO public AS
$$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(NEW.bug));
        ELSE
            PERFORM summarise_bug(bug_row(NEW.bug));
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        IF TG_WHEN = 'BEFORE' THEN
            PERFORM unsummarise_bug(bug_row(OLD.bug));
        ELSE
            PERFORM summarise_bug(bug_row(OLD.bug));
        END IF;
        RETURN OLD;
    ELSE
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
        RETURN NEW;
    END IF;
END;
$$;

COMMENT ON FUNCTION bugtag_maintain_bug_summary() IS
'AFTER trigger on bugtag maintaining the bugs summaries in bugsummary.';


-- we need to maintain the summaries when things change. Each variable the
-- population script above uses needs to be accounted for.

-- bug: duplicateof, private (not INSERT because a task is needed to be included in summaries.
CREATE TRIGGER bug_maintain_bug_summary_trigger
AFTER UPDATE OR DELETE ON bug
FOR EACH ROW EXECUTE PROCEDURE bug_maintain_bug_summary();

-- bugtask: target, status, milestone
CREATE TRIGGER bugtask_maintain_bug_summary_before_trigger
BEFORE INSERT OR UPDATE OR DELETE ON bugtask
FOR EACH ROW EXECUTE PROCEDURE bugtask_maintain_bug_summary();

CREATE TRIGGER bugtask_maintain_bug_summary_after_trigger
AFTER INSERT OR UPDATE OR DELETE ON bugtask
FOR EACH ROW EXECUTE PROCEDURE bugtask_maintain_bug_summary();

-- bugsubscription: existence
CREATE TRIGGER bugsubscription_maintain_bug_summary_before_trigger
BEFORE INSERT OR UPDATE OR DELETE ON bugsubscription
FOR EACH ROW EXECUTE PROCEDURE bugsubscription_maintain_bug_summary();

CREATE TRIGGER bugsubscription_maintain_bug_summary_after_trigger
AFTER INSERT OR UPDATE OR DELETE ON bugsubscription
FOR EACH ROW EXECUTE PROCEDURE bugsubscription_maintain_bug_summary();

-- bugtag: existence
CREATE TRIGGER bugtag_maintain_bug_summary_before_trigger
BEFORE INSERT OR UPDATE OR DELETE ON bugtag
FOR EACH ROW EXECUTE PROCEDURE bugtag_maintain_bug_summary();

CREATE TRIGGER bugtag_maintain_bug_summary_after_trigger
AFTER INSERT OR UPDATE OR DELETE ON bugtag
FOR EACH ROW EXECUTE PROCEDURE bugtag_maintain_bug_summary();

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 63, 0);
