SET client_min_messages=ERROR;

--Create new visible column on message.
ALTER TABLE Message
    ADD COLUMN visible BOOLEAN NOT NULL DEFAULT TRUE;

--Migrate the data, rebuilding indexes afterwards.
UPDATE Message SET visible = FALSE
    FROM BugMessage
    WHERE BugMessage.message = Message.id AND BugMessage.visible IS FALSE;
CLUSTER Message USING message_pkey;

--And kill the old column
ALTER TABLE BugMessage
    DROP COLUMN visible;

--Per patch adding reqs
INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 51, 0);
