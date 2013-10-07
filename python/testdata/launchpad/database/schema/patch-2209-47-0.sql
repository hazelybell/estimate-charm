-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE job ADD COLUMN json_data TEXT;
ALTER TABLE job ADD COLUMN job_type INTEGER;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 47, 0);
