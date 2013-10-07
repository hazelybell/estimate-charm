-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE binarypackagebuild
    DROP COLUMN package_build,
    ALTER COLUMN archive SET NOT NULL,
    ALTER COLUMN pocket SET NOT NULL,
    ALTER COLUMN date_created SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN failure_count SET NOT NULL,
    ALTER COLUMN build_farm_job SET NOT NULL,
    ALTER COLUMN distribution SET NOT NULL,
    ALTER COLUMN distro_series SET NOT NULL,
    ALTER COLUMN distro_arch_series SET NOT NULL,
    ALTER COLUMN is_distro_archive SET NOT NULL,
    ALTER COLUMN source_package_name SET NOT NULL;

ALTER TABLE sourcepackagerecipebuild
    DROP COLUMN package_build,
    ALTER COLUMN archive SET NOT NULL,
    ALTER COLUMN pocket SET NOT NULL,
    ALTER COLUMN date_created SET NOT NULL,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN failure_count SET NOT NULL,
    ALTER COLUMN build_farm_job SET NOT NULL;

ALTER TABLE buildfarmjob
    DROP COLUMN processor,
    DROP COLUMN virtualized,
    DROP COLUMN date_started,
    DROP COLUMN date_first_dispatched,
    DROP COLUMN log,
    DROP COLUMN failure_count;

DROP TABLE packagebuild;

DROP INDEX buildfarmjob__builder_and_status__idx;
DROP INDEX buildfarmjob__date_created__idx;
DROP INDEX buildfarmjob__date_finished__idx;
DROP INDEX buildfarmjob__status__id__idx;
DROP INDEX buildfarmjob__status__idx;

DROP INDEX binarypackagebuild__distro_arch_series__idx;
DROP INDEX binarypackagebuild__das__id__idx;
DROP INDEX binarypackagebuild__das__status__date_finished__id__idx;
DROP INDEX binarypackagebuild__das__status__id__idx;
DROP INDEX binarypackagebuild__source_package_release_idx;

ALTER INDEX binarypackagebuild__das__id__2__idx
    RENAME TO binarypackagebuild__das__id__idx;
ALTER INDEX binarypackagebuild__das__status__date_finished__id__2__idx
    RENAME TO binarypackagebuild__das__status__date_finished__id__idx;
ALTER INDEX binarypackagebuild__das__status__id__2__idx
    RENAME TO binarypackagebuild__das__status__id__idx;

DROP INDEX sourcepackagerecipebuild__recipe__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 5);
