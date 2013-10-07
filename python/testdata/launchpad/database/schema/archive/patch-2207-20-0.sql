SET client_min_messages=ERROR;

-- Drop the old view.
DROP VIEW validpersonorteamcache;

-- Create the new view that excludes merged teams.
CREATE VIEW validpersonorteamcache AS
    SELECT person.id FROM
    ((person LEFT JOIN emailaddress ON ((person.id = emailaddress.person))) LEFT JOIN account ON ((emailaddress.account = account.id)))
    WHERE (((person.teamowner IS NOT NULL) AND (person.merged IS NULL)) OR
    (person.teamowner IS NULL AND (account.status = 20) AND (emailaddress.status = 4)));

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 20, 0);
