-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE INDEX binarypackagepublishinghistory__binarypackagename__idx ON BinaryPackagePublishingHistory(binarypackagename);
CREATE INDEX sourcepackagepublishinghistory__sourcepackagename__idx ON SourcePackagePublishingHistory(sourcepackagename);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 87, 2);

