-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- The schema patch required for the Soyuz buildd generalisation, see
-- https://dev.launchpad.net/Soyuz/Specs/BuilddGeneralisation for details.
-- Bug #485524.

-- Please note : this change is needed in order to estimate build farm job
-- dispatch times irrespective of the job type.

-- Step 1
-- Add an estimated duration column to the `BuildQueue` table first.
ALTER TABLE ONLY buildqueue
ADD COLUMN estimated_duration interval NOT NULL DEFAULT '0 sec';

-- Step 2
-- Migrate the estimated duration values from the `Build` table.
UPDATE buildqueue
    SET estimated_duration = build.estimated_build_duration
    FROM buildpackagejob, build
    WHERE
        buildqueue.job = buildpackagejob.job
        AND buildpackagejob.build = build.id
        AND build.estimated_build_duration IS NOT NULL;

-- Step 3
-- Drop the obsolete 'estimated_build_duration' column from the `Build` table.
ALTER TABLE ONLY build DROP COLUMN estimated_build_duration;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 14, 0);
