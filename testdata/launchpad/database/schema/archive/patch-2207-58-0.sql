-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE SourcePackageRecipe
   DROP COLUMN sourcepackagename;

ALTER TABLE SourcePackageRecipeBuild
   DROP COLUMN sourcepackagename;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 58, 0);
