SET client_min_messages=ERROR;

UPDATE BugWatchActivity SET result = 9 WHERE result IS NULL;
ALTER TABLE BugWatchActivity ALTER COLUMN result SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 47, 0);
