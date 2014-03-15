-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE SourcePackageRecipeBuildJob
    ALTER COLUMN sourcepackage_recipe_build SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 16, 0);
