-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE oauthnonce DROP CONSTRAINT oauthnonce_pkey;
ALTER TABLE oauthnonce DROP CONSTRAINT
    oauthnonce__access_token__request_timestamp__nonce__key;
ALTER TABLE oauthnonce ADD PRIMARY KEY
    (access_token, request_timestamp, nonce);

ALTER TABLE oauthnonce DROP COLUMN id;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 77, 0);

