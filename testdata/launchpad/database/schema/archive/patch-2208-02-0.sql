SET client_min_messages=ERROR;

CREATE TABLE OpenIdIdentifier (
    identifier text PRIMARY KEY,
    account integer NOT NULL REFERENCES Account ON DELETE CASCADE,
    date_created timestamp without time zone NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

CREATE INDEX openididentifier__account__idx ON OpenIDIdentifier(account);


-- XXX: Should data be migrated? Existing data is just tokens, not the
-- full URL. If we can convert this old data to URLs, we should add a
-- CHECK constraint to OpenIDIdentifier.identifier too.
INSERT INTO OpenIdIdentifier (identifier, account, date_created)
SELECT openid_identifier, id, date_created FROM Account;

ALTER TABLE Account
    DROP COLUMN openid_identifier,
    DROP COLUMN old_openid_identifier;

DROP TRIGGER lp_mirror_account_del_t ON Account;
DROP TRIGGER lp_mirror_account_ins_t ON Account;
DROP TRIGGER lp_mirror_account_upd_t ON Account;

CREATE TRIGGER lp_mirror_openididentifier_ins_t
AFTER INSERT ON OpenIdIdentifier FOR EACH ROW
EXECUTE PROCEDURE lp_mirror_openididentifier_ins();

CREATE TRIGGER lp_mirror_openididentifier_upd_t
AFTER UPDATE ON OpenIdIdentifier FOR EACH ROW
EXECUTE PROCEDURE lp_mirror_openididentifier_upd();

CREATE TRIGGER lp_mirror_openididentifier_del_t
AFTER DELETE ON OpenIdIdentifier FOR EACH ROW
EXECUTE PROCEDURE lp_mirror_openididentifier_del();


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 02, 0);
