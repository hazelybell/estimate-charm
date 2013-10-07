-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE distroseries
    ADD COLUMN proposed_not_automatic BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 25, 1);
