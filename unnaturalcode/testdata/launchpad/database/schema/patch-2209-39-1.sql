SET client_min_messages=ERROR;

ALTER TABLE LibraryFileAlias DROP COLUMN last_accessed;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 39, 1);
