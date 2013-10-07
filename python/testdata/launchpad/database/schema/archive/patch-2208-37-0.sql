-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE StructuralSubscription
    DROP COLUMN bug_notification_level;
ALTER TABLE BugSubscriptionFilter
    ADD COLUMN bug_notification_level
        integer DEFAULT 40 NOT NULL;
CREATE INDEX bugsubscriptionfilter__bug_notification_level__idx ON bugsubscriptionfilter USING btree (bug_notification_level);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 37, 0);
