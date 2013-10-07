-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- A table to store bug mutes in.

CREATE TABLE BugMute (
    person integer REFERENCES Person(id)
        ON DELETE CASCADE NOT NULL,
    bug integer REFERENCES Bug(id)
        ON DELETE CASCADE NOT NULL,
    date_created timestamp without time zone
        DEFAULT timezone('UTC'::text, now()) NOT NULL,
    CONSTRAINT bugmute_pkey PRIMARY KEY (person, bug)
);

-- We don't need an index on person, as the primary key index can be used
-- for those lookups. We have an index on just the bug, as the bulk of our
-- lookups will be on bugs.
CREATE INDEX bugmute__bug__idx
    ON BugMute(bug);

-- Migrate existing BugSubscription's with
-- bug_notification_level == NOTHING
-- to BugMute table.
INSERT INTO BugMute (person, bug, date_created)
    SELECT person, bug, date_created
        FROM BugSubscription
        WHERE bug_notification_level=10;
-- Remove 'muting' BugSubscriptions.
DELETE
    FROM BugSubscription
    WHERE bug_notification_level=10;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 70, 0);
