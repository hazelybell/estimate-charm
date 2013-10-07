-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE archive ADD COLUMN permit_obsolete_series_uploads boolean;
ALTER TABLE archive ALTER COLUMN permit_obsolete_series_uploads
    SET DEFAULT false;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 46, 0);
