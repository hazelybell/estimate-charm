SET client_min_messages=ERROR;

ALTER TABLE Archive
    ADD COLUMN commercial BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX archive__commercial__idx ON Archive(commercial);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 63, 0);
