-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE Distribution
    ADD COLUMN redirect_release_uploads BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 36, 0);
