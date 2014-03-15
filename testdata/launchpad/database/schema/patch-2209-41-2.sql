-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Fix defaults that were intended to be set by 2209-41-0.
ALTER TABLE translationtemplatesbuild
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    ALTER COLUMN failure_count SET DEFAULT 0;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 2);
