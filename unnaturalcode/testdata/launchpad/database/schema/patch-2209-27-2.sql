-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE ProcessAcceptedBugsJob (
    job integer PRIMARY KEY REFERENCES Job ON DELETE CASCADE UNIQUE NOT NULL,
    distroseries integer REFERENCES DistroSeries NOT NULL,
    sourcepackagerelease integer REFERENCES SourcePackageRelease NOT NULL,
    json_data text
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 27, 2);
