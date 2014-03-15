SET client_min_messages=ERROR;

ALTER TABLE PersonSettings
  ALTER COLUMN selfgenerated_bugnotifications SET DEFAULT FALSE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 44, 0);
