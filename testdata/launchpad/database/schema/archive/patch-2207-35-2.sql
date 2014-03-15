SET client_min_messages=ERROR;

/* This table is populated and triggers added to keep it up to date
in patch-2207-44-0.sql. The table creation is in a separate DB
patch to we can install it on production before rollout and grant
required permissions. */
CREATE TABLE lp_Account (
    id integer PRIMARY KEY,
    openid_identifier text NOT NULL
        CONSTRAINT lp_account__openid_identifier__key UNIQUE);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 35, 2);
