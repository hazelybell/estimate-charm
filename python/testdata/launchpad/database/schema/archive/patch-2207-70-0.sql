SET client_min_messages=ERROR;

ALTER TABLE Person
    DROP COLUMN addressline1,
    DROP COLUMN addressline2,
    DROP COLUMN organization,
    DROP COLUMN city,
    DROP COLUMN province,
    DROP COLUMN country,
    DROP COLUMN postcode,
    DROP COLUMN phone;


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 70, 0);
