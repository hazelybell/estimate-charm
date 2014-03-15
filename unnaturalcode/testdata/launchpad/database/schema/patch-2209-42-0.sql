-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- statement_timestamp() is the time of the last client command, which
-- isn't what we want here (the patch is run by a single execute call).
-- clock_timestamp() is whatever the actual execution time was.
ALTER TABLE launchpaddatabaserevision ALTER COLUMN end_time
    SET DEFAULT (clock_timestamp() AT TIME ZONE 'UTC');

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 42, 0);
