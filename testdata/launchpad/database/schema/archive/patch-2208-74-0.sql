-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE CodeImport DROP CONSTRAINT valid_vcs_details;
ALTER TABLE CodeImport ADD CONSTRAINT "valid_vcs_details" CHECK (
CASE
    WHEN rcs_type = 1 THEN cvs_root IS NOT NULL AND cvs_root <> ''::text AND cvs_module IS NOT NULL AND cvs_module <> ''::text AND url IS NULL
    WHEN rcs_type IN (2, 3) THEN cvs_root IS NULL AND cvs_module IS NULL AND url IS NOT NULL AND valid_absolute_url(url)
    WHEN rcs_type IN (4, 5, 6) THEN cvs_root IS NULL AND cvs_module IS NULL AND url IS NOT NULL
    ELSE false
END);


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 74, 0);

