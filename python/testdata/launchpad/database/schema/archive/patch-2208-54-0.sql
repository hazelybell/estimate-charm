SET client_min_messages=ERROR;

ALTER TABLE distroarchseries
    ADD CONSTRAINT valid_architecturetag CHECK (valid_name(architecturetag));

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 54, 0);
