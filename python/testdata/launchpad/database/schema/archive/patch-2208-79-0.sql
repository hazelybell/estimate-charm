-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE distroseries
    ADD COLUMN include_long_descriptions BOOLEAN NOT NULL DEFAULT TRUE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 79, 0);
