-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE SourcePackagePublishingHistory
ALTER COLUMN sourcepackagename SET NOT NULL;
ALTER TABLE BinaryPackagePublishingHistory
ALTER COLUMN binarypackagename SET NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 00, 1);
