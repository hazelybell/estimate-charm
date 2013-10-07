-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Archive
RENAME COLUMN commercial TO suppress_subscription_notifications;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 22, 0);
