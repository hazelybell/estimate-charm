-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE TranslationMessage
    DROP COLUMN variant;
ALTER TABLE POFile
    DROP COLUMN variant;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 29, 0);
