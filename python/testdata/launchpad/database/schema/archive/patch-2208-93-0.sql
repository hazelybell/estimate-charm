SET client_min_messages=ERROR;

/* POFileStatsJob holds scheduled jobs that are to update POFile statistics */
CREATE TABLE POFileStatsJob (
    job          INTEGER NOT NULL UNIQUE REFERENCES Job(id) PRIMARY KEY,
    pofile       INTEGER NOT NULL REFERENCES POFile(id)
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 93, 0);
