-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE processorfamily ADD COLUMN restricted boolean DEFAULT FALSE NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 35, 0);
