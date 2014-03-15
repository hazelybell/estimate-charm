SET client_min_messages=ERROR;

ALTER TABLE BugNotificationRecipient
    DROP CONSTRAINT bugnotificationrecipient_bug_notification_fkey,
    ADD CONSTRAINT bugnotificationrecipient__bug_notification__fk
        FOREIGN KEY (bug_notification) REFERENCES BugNotification
            ON DELETE CASCADE;

ALTER TABLE BugNotificationAttachment
    DROP CONSTRAINT bugnotificationattachment_bug_notification_fkey,
    ADD CONSTRAINT bugnotificationattachment__bug_notification__fk
        FOREIGN KEY (bug_notification) REFERENCES BugNotification
            ON DELETE CASCADE;

-- Backup historical data until we can deal with it per Bug #407288.
-- We keep the person foreign key constraint so this data is modified
-- by Person merges.
-- These two tables need to be populated manually after rollout and before
-- garbo-daily.py is run.
CREATE TABLE BugNotificationArchive AS
    SELECT * FROM BugNotification WHERE FALSE;
ALTER TABLE BugNotificationArchive
    ADD CONSTRAINT bugnotificationarchive__bug__message__key
        UNIQUE (bug, message);
ALTER TABLE BugNotificationArchive
    ADD CONSTRAINT bugnotificationarchive_pk PRIMARY KEY (id),
    ADD CONSTRAINT bugnotificationarchive__message__fk
        FOREIGN KEY (message) REFERENCES Message,
    ADD CONSTRAINT bugnotificationarchive__bug__fk
        FOREIGN KEY (bug) REFERENCES Bug;
CREATE TABLE BugNotificationRecipientArchive AS
    SELECT * FROM BugNotificationRecipient WHERE FALSE;
CREATE INDEX bugnotificationrecipientarchive__person__idx
    ON bugnotificationrecipientarchive(person);
CREATE INDEX bugnotificationrecipientarchive__bug_notification__idx
    ON BugNotificationRecipientArchive(bug_notification);
ALTER TABLE bugnotificationrecipientarchive 
    ADD CONSTRAINT bugnotificationrecipientarchive_pk PRIMARY KEY (id),
    ADD CONSTRAINT bugnotificationrecipientarchive__person__fk
        FOREIGN KEY (person) REFERENCES Person,
    ADD CONSTRAINT bugnotificationrecipientarchive__bug_notification__fk
        FOREIGN KEY (bug_notification) REFERENCES BugNotificationArchive;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 2, 0);

