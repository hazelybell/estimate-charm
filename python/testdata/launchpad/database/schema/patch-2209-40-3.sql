-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE packageupload
    ALTER COLUMN searchable_names SET NOT NULL,
    ALTER COLUMN searchable_versions SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 40, 3);
