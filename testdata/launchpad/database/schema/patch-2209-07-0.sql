-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

DROP TRIGGER tsvectorupdate ON bugtask;
ALTER TABLE bugtask DROP COLUMN fti;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 07, 0);
