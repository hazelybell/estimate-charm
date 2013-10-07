-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE product ADD COLUMN max_bug_heat integer;
ALTER TABLE project ADD COLUMN max_bug_heat integer;
ALTER TABLE distribution ADD COLUMN max_bug_heat integer;
ALTER TABLE distributionsourcepackage ADD COLUMN max_bug_heat integer;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 34, 0);
