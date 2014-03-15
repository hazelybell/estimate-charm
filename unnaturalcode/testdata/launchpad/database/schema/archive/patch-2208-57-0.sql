SET client_min_messages=ERROR;

ALTER TABLE distroseries
    ADD COLUMN backports_not_automatic BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 57, 0);
