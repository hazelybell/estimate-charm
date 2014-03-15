SET client_min_messages=ERROR;

DROP INDEX emailaddress__lower_email__key;
CREATE UNIQUE INDEX emailaddress__lower_email__key
        ON EmailAddress(lower(email));

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 35, 1);
