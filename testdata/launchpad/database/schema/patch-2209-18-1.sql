-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE ArchivePermission DROP CONSTRAINT one_target;

ALTER TABLE ArchivePermission ADD COLUMN pocket INTEGER;

ALTER TABLE ArchivePermission ADD CONSTRAINT one_target CHECK ((null_count(ARRAY[packageset, component, sourcepackagename, pocket]) = 3));

COMMENT ON COLUMN ArchivePermission.pocket IS 'The pocket to which this permission applies.';

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 18, 1);
