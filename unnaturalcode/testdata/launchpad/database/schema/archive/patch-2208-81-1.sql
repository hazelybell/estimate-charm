-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE SourcePackagePublishingHistory ADD COLUMN sourcepackagename INTEGER REFERENCES SourcePackageName;
ALTER TABLE BinaryPackagePublishingHistory ADD COLUMN binarypackagename INTEGER REFERENCES BinaryPackageName;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 81, 1);

