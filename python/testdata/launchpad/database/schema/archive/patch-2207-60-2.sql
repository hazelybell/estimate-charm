SET client_min_messages=ERROR;

CREATE INDEX job__date_finished__idx ON Job(date_finished)
WHERE date_finished IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 60, 2);

