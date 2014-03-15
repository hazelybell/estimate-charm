-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE OR REPLACE VIEW validpersoncache AS (
    SELECT emailaddress.person AS id
    FROM emailaddress, person, account
    WHERE
        emailaddress.person = person.id
        AND person.account = account.id
        AND emailaddress.status = 4
        AND account.status = 20
);

CREATE OR REPLACE VIEW validpersonorteamcache AS (
    SELECT person.id
    FROM
        person
        LEFT JOIN emailaddress ON person.id = emailaddress.person
        LEFT JOIN account ON person.account = account.id
    WHERE
        (person.teamowner IS NOT NULL
         AND person.merged IS NULL)
        OR
        (person.teamowner IS NULL
         AND account.status = 20
         AND emailaddress.status = 4)
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 01, 0);
