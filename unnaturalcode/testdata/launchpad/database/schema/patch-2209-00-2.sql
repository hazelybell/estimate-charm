-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- deb-version in recipes is optional in newer versions of bzr-builder:
ALTER TABLE SourcePackageRecipeData ALTER COLUMN deb_version_template DROP NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 2);
