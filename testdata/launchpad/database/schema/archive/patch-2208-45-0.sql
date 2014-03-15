-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- The default value for status can be found in the
-- BugNotificationStatus DBEnum in lib/lp/bugs/enum.py.
ALTER TABLE BugNotification
    ADD COLUMN status INTEGER NOT NULL DEFAULT 10;

CLUSTER BugNotification USING bugnotification__date_emailed__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 45, 0);
