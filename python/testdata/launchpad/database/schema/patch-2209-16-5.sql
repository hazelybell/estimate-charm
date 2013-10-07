-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

DROP TRIGGER bug_to_bugtask_heat ON bug;
DROP FUNCTION bug_update_heat_copy_to_bugtask();

ALTER TABLE BugTask DROP COLUMN binarypackagename;
ALTER TABLE BugTask DROP COLUMN heat;
ALTER TABLE BugTask DROP COLUMN heat_rank;
ALTER TABLE Bug DROP COLUMN private;
ALTER TABLE Bug DROP COLUMN security_related;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 5);
