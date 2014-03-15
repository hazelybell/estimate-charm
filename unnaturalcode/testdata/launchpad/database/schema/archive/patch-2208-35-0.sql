SET client_min_messages=ERROR;

ALTER TABLE distribution DROP COLUMN lucilleconfig;
ALTER TABLE distroseries DROP COLUMN lucilleconfig;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 35, 0);

