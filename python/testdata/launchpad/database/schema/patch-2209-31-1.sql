-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE product ADD COLUMN specification_sharing_policy integer;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 31, 1);
