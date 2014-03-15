-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE BinaryPackageRelease
    ADD COLUMN homepage TEXT;

ALTER TABLE SourcePackageRelease
    ADD COLUMN homepage TEXT;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 05, 0);
