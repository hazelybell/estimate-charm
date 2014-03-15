-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE distribution
    ADD COLUMN package_derivatives_email TEXT;
UPDATE distribution
    SET package_derivatives_email = '{package_name}_derivatives@packages.qa.debian.org'
    WHERE name='ubuntu';

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 80, 1);
