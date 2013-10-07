SET client_min_messages=ERROR;

INSERT INTO PersonSettings (person)
    SELECT id FROM Person WHERE teamowner IS NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 38, 1);


