-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE processor ALTER COLUMN restricted SET NOT NULL;
ALTER TABLE processor ALTER COLUMN family DROP NOT NULL;

ALTER TABLE distroarchseries ALTER COLUMN processor SET NOT NULL;
ALTER TABLE distroarchseries ALTER COLUMN processorfamily DROP NOT NULL;

ALTER TABLE archivearch ALTER COLUMN processor SET NOT NULL;
ALTER TABLE archivearch ALTER COLUMN processorfamily DROP NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 49, 1);
