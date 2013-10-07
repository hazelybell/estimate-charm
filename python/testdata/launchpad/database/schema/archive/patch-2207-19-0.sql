-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- This schema patch introduces the missing constraints related to
-- the BuildQueue, BuildPackageJob, Build and Job tables:
--
--  - unique index on BuildPackageJob.build
--  - unique index on BuildPackageJob.job
--  - unique index on BuildQueue.job
--
-- after performing the following database clean-up actions:
--
--  1 - remove all BuildQueue rows for Build records that are not in
--      state NEEDSBUILD or BUILDING
--  2 - remove all *duplicate* BuildQueue rows for Build records that *are*
--      in state NEEDSBUILD or BUILDING
--  3 - remove all BuildPackageJob and Job rows that do not have a
--      BuildQueue row associated with them

-- Step 1
-- Data clean-up
DELETE FROM BuildQueue USING BuildPackageJob, Build
WHERE
    BuildQueue.job = BuildPackageJob.job
    AND BuildPackageJob.build = Build.id
    -- NOT IN (NEEDSBUILD, BUILDING)
    AND Build.buildstate NOT IN (0,6);

CREATE OR REPLACE FUNCTION cleanup_buildqueue_rows() RETURNS integer
LANGUAGE plpgsql AS
$$
DECLARE
    build_stats RECORD;
    most_recent_buildqueue integer;
    orphaned_buildpackagejob RECORD;
    builds_with_duplicate_bq_rows integer;
BEGIN
    builds_with_duplicate_bq_rows := 0;
    -- Iterate over all Build records with duplicate BuildQueue rows.
    FOR build_stats IN
        SELECT Build.id AS build_id, COUNT(BuildQueue.id)
        FROM Build, BuildQueue, BuildPackageJob
        WHERE
            BuildQueue.job = BuildPackageJob.job
            AND BuildPackageJob.build = Build.id
        GROUP BY Build.id
        HAVING COUNT(BuildQueue.id) > 1
    LOOP
        builds_with_duplicate_bq_rows := builds_with_duplicate_bq_rows + 1;
        -- Find the most recent BuildQueue row for this Build record.
        SELECT BuildQueue.id INTO most_recent_buildqueue
        FROM Build, BuildQueue, BuildPackageJob
        WHERE
            BuildQueue.job = BuildPackageJob.job
            AND BuildPackageJob.build = Build.id
            AND Build.id = build_stats.build_id
        ORDER BY BuildQueue.id DESC LIMIT 1;

        -- Delete all but the most recent BuildQueue row for this Build
        -- record.
        DELETE FROM BuildQueue USING BuildPackageJob, Build
        WHERE
            BuildQueue.job = BuildPackageJob.job
            AND BuildPackageJob.build = Build.id
            AND Build.id = build_stats.build_id
            AND BuildQueue.id != most_recent_buildqueue;
    END LOOP;

    -- Iterate over all BuildPackageJob/Job rows *not* associated with
    -- a BuildQueue record.
    FOR orphaned_buildpackagejob IN
        SELECT id, job FROM buildpackagejob
        WHERE NOT EXISTS(
            SELECT id FROM buildqueue
            WHERE buildqueue.job = buildpackagejob.job)
    LOOP
        DELETE FROM BuildPackageJob WHERE id = orphaned_buildpackagejob.id;
        DELETE FROM Job WHERE id = orphaned_buildpackagejob.job;
    END LOOP;

    RETURN builds_with_duplicate_bq_rows;
END;
$$;

-- Run the data clean-up function and drop it.
SELECT * FROM cleanup_buildqueue_rows();
DROP FUNCTION cleanup_buildqueue_rows();

-- Step 2
-- Create unique indices.
-- We need to drop the `buildqueue__job__idx` and recreate it as a *unique*
-- index.
DROP INDEX buildqueue__job__idx;
ALTER TABLE BuildQueue ADD CONSTRAINT buildqueue__job__key UNIQUE (job);

ALTER TABLE BuildPackageJob
    ADD CONSTRAINT buildpackagejob__job__key UNIQUE (job);
ALTER TABLE BuildPackageJob
    ADD CONSTRAINT buildpackagejob__build__key UNIQUE (build);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 19, 0);
