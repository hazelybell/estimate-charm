-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE product ALTER COLUMN information_type SET DEFAULT 1;
ALTER TABLE product ALTER COLUMN information_type SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 35, 3);
