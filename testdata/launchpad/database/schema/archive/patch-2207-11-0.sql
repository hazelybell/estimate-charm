-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- The schema patch required for the Soyuz buildd generalisation, see
-- https://dev.launchpad.net/Soyuz/Specs/BuilddGeneralisation for details.
-- Bug #478919.

-- Step 1
-- The `BuildPackageJob` table captures whatever data is required for
-- "normal" Soyuz build farm jobs that build source packages.

CREATE TABLE buildpackagejob (
  id serial PRIMARY KEY,
  -- FK to the `Job` record with "generic" data about this source package
  -- build job. Please note that the corresponding `BuildQueue` row will
  -- have a FK referencing the same `Job` row.
  job integer NOT NULL CONSTRAINT buildpackagejob__job__fk REFERENCES job,
  -- FK to the associated `Build` record.
  build integer NOT NULL CONSTRAINT buildpackagejob__build__fk REFERENCES build
);

-- Step 2
-- Changes needed to the `BuildQueue` table.

-- The 'job' and the 'job_type' columns will enable us to find the correct
-- database rows that hold the generic and the specific data pertaining to
-- the job respectively.
ALTER TABLE ONLY buildqueue ADD COLUMN job integer;
ALTER TABLE ONLY buildqueue ADD COLUMN job_type integer NOT NULL DEFAULT 1;

-- Step 3
-- Data migration for the existing `BuildQueue` records.
CREATE OR REPLACE FUNCTION migrate_buildqueue_rows() RETURNS integer
LANGUAGE plpgsql AS
$$
DECLARE
    queue_row RECORD;
    job_id integer;
    buildpackagejob_id integer;
    rows_migrated integer;
BEGIN
    rows_migrated := 0;
    FOR queue_row IN SELECT * FROM buildqueue LOOP
        INSERT INTO job(status, date_created, date_started) VALUES(0, queue_row.created, queue_row.buildstart);
        -- Get the key of the `Job` row just inserted.
        SELECT currval('job_id_seq') INTO job_id;
        INSERT INTO buildpackagejob(job, build) VALUES(job_id, queue_row.build);
        -- Get the key of the `BuildPackageJob` row just inserted.
        SELECT currval('buildpackagejob_id_seq') INTO buildpackagejob_id;
        UPDATE buildqueue SET job=job_id WHERE id=queue_row.id;
        rows_migrated := rows_migrated + 1;
    END LOOP;
    RETURN rows_migrated;
END;
$$;

-- Run the data migration function.
SELECT * FROM migrate_buildqueue_rows();
-- The `BuildQueue` data is migrated at this point, we can get rid of the
-- data migration function.
DROP FUNCTION migrate_buildqueue_rows();

-- Now that the data was migrated we can make the 'job' column mandatory
-- and define the foreign key constraint for it.
ALTER TABLE ONLY buildqueue ALTER COLUMN job SET NOT NULL;
ALTER TABLE ONLY buildqueue
    ADD CONSTRAINT buildqueue__job__fk
    FOREIGN KEY (job) REFERENCES job(id);

-- Step 4
-- Now remove the obsolete columns, constraints and indexes from `BuildQueue`.
-- The latter will from now on refer to the `Build` record via the
-- `Job`/`BuildPackageJob` tables (and not directly any more).
DROP INDEX buildqueue__build__idx;
ALTER TABLE ONLY buildqueue DROP CONSTRAINT "$1";
ALTER TABLE ONLY buildqueue DROP COLUMN build;
ALTER TABLE ONLY buildqueue DROP COLUMN created;
ALTER TABLE ONLY buildqueue DROP COLUMN buildstart;

-- Step 5
-- Add indexes for the new `BuildQueue` columns.
CREATE INDEX buildqueue__job__idx ON buildqueue(job);
CREATE INDEX buildqueue__job_type__idx ON buildqueue(job_type);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 11, 0);
