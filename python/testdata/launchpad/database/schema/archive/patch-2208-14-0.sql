SET client_min_messages=ERROR;

-- Store the row index of bug messages so we don't have to calculate it all the time.
ALTER TABLE BugMessage ADD COLUMN index integer;

-- BugMessage.indexes must be unique per bug.
ALTER TABLE BugMessage ADD CONSTRAINT bugmessage__bug__index__key UNIQUE (bug, index);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 14, 0);
