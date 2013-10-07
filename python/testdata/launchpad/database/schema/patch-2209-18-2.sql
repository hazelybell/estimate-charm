-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Builder ALTER COLUMN description DROP NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 18, 2);
