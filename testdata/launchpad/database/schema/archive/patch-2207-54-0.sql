-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE SourcePackageRecipe
   ADD COLUMN daily_build_archive integer REFERENCES Archive;

CREATE INDEX sourcepackagerecipe__daily_build_archive__idx ON SourcepackageRecipe(daily_build_archive);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 54, 0);
