SET client_min_messages=ERROR;

CREATE TABLE lp_OpenIdIdentifier (
    identifier text PRIMARY KEY,
    account    integer NOT NULL,
    date_created timestamp without time zone NOT NULL);

INSERT INTO lp_OpenIdIdentifier (identifier, account, date_created)
SELECT identifier, account, date_created FROM OpenIdIdentifier
WHERE identifier NOT IN (SELECT identifier FROM lp_OpenIdIdentifier);

CREATE INDEX lp_openididentifier__account__idx
ON lp_OpenIdIdentifier(account);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 21, 0);
