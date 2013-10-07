-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- The default value for bug_notification_level can be found in the
-- BugNotificationLevel DBEnum in
-- lib/lp/registry/interfaces/structuralsubscription.py.
ALTER TABLE BugSubscription
    ADD COLUMN bug_notification_level INTEGER NOT NULL DEFAULT 40;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 76, 0);
