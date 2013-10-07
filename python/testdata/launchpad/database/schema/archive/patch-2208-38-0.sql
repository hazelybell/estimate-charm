SET client_min_messages=ERROR;

CREATE TABLE PersonSettings (
    person integer PRIMARY KEY REFERENCES Person ON DELETE CASCADE,
    selfgenerated_bugnotifications boolean NOT NULL DEFAULT TRUE);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 38, 0);
