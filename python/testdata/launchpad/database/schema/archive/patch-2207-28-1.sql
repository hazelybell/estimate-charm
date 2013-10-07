SET client_min_messages = ERROR;

CREATE TABLE DatabaseReplicationLag (
    node integer PRIMARY KEY,
    lag interval NOT NULL,
    updated timestamp without time zone
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'));

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 28, 1);
