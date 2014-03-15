-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE ParsedApacheLog
    ALTER COLUMN bytes_read TYPE bigint;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 32, 0);
