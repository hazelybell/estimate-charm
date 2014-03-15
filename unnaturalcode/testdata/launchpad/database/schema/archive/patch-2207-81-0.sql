-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- The default value of 10 from lp.app.enums is UNKNOWN.
ALTER TABLE Product
    ADD COLUMN answers_usage INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN blueprints_usage INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN translations_usage INTEGER NOT NULL DEFAULT 10,
    DROP COLUMN official_codehosting;

ALTER TABLE Distribution
    ADD COLUMN answers_usage INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN blueprints_usage INTEGER NOT NULL DEFAULT 10,
    ADD COLUMN translations_usage INTEGER NOT NULL DEFAULT 10;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 81, 0);
