-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Drop the statusexplanation column from bugtask

ALTER TABLE bugtask DROP COLUMN statusexplanation;
DROP TRIGGER tsvectorupdate ON bugtask;
CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE ON bugtask FOR EACH ROW EXECUTE PROCEDURE ftiupdate('targetnamecache', 'b');

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 84, 1);
