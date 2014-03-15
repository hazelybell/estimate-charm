-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- In DistroSeriesDifference, the constraint UNIQUE (derived_series, source_package_name) 
-- should be UNIQUE (derived_series, parent_series, source_package_name).
ALTER TABLE DistroSeriesDifference
    DROP CONSTRAINT "distroseriesdifference__derived_series__source_package_name__key";

ALTER TABLE DistroSeriesDifference
    ADD CONSTRAINT distroseriesdifference__derived_series__parent_series__source_package_name__key
        UNIQUE (derived_series, parent_series, source_package_name);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 67, 0);
