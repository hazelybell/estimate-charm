-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE processor DROP COLUMN family;
ALTER TABLE distroarchseries DROP COLUMN processorfamily;
ALTER TABLE archivearch DROP COLUMN processorfamily;

DROP TABLE processorfamily;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 49, 2);
