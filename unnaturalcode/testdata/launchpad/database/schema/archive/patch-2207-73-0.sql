-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

ALTER TABLE BinaryPackageRelease
    ADD COLUMN debug_package integer REFERENCES BinaryPackageRelease;

CREATE UNIQUE INDEX binarypackagerelease__debug_package__key
    ON BinaryPackageRelease(debug_package);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 73, 0);
