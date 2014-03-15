-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

DROP TRIGGER bug_mirror_legacy_access_t ON bug;
DROP TRIGGER bugtask_mirror_legacy_access_t ON bugtask;
DROP TRIGGER bugsubscription_mirror_legacy_access_t ON bugsubscription;
DROP FUNCTION bug_mirror_legacy_access_trig();
DROP FUNCTION bugtask_mirror_legacy_access_trig();
DROP FUNCTION bugsubscription_mirror_legacy_access_trig();
DROP FUNCTION bug_mirror_legacy_access(bug_id integer);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 7);
