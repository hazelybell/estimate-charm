-- Copyright 2010 Canonical Ltd. This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TEMPORARY TABLE BuildInfo AS
SELECT
    build.id,
    build.processor,
    archive.require_virtualized AS virtualized,
    -- Currently we do not know if a build was virtual or not? (it's
    -- only on the archive and the builder, both of which can
    -- change). IBuild.is_virtualized just queries the archive.
    build.datecreated AS date_created,
    (build.datebuilt - build.buildduration) AS date_started,
    build.datebuilt AS date_finished,
    build.date_first_dispatched,
    build.builder,
    build.buildstate AS status,
    build.buildlog AS log,
    build.archive,
    build.pocket,
    build.upload_log,
    build.dependencies,
    build.distroarchseries AS distro_arch_series,
    build.sourcepackagerelease AS source_package_release,
    build.build_warnings -- We don't seem to use this in LP code at all?
FROM build JOIN archive ON build.archive = archive.id;

-- The schema patch for general build histories. See
-- https://dev.launchpad.net/LEP/GeneralBuildHistories and the linked
-- blueprint/bug for more information.

-- Step 1
-- Create the new BuildFarmJob, PackageBuild and BinaryPackageBuild tables,
-- with indexes based on the current Build table.
CREATE TABLE BuildFarmJob (
    id serial PRIMARY KEY,
    processor integer
        CONSTRAINT buildfarmjob__processor__fk REFERENCES processor,
    virtualized boolean,
    date_created timestamp without time zone
        DEFAULT timezone('UTC'::text, now()) NOT NULL,
    date_started timestamp without time zone,
    date_finished timestamp without time zone,
    date_first_dispatched timestamp without time zone,
    builder integer CONSTRAINT buildfarmjob__builder__fk REFERENCES builder,
    status integer NOT NULL,
    log integer CONSTRAINT buildfarmjob__log__fk REFERENCES libraryfilealias,
    job_type integer NOT NULL
);

INSERT INTO BuildFarmJob (
    id, processor, virtualized, date_created, date_started,
    date_finished, builder, status, log, job_type)
SELECT
    id, processor, virtualized, date_created, date_started,
    date_finished, builder, status, log, 1
FROM BuildInfo;

SELECT setval('buildfarmjob_id_seq', MAX(id)) FROM BuildFarmJob;

CREATE INDEX buildfarmjob__date_created__idx ON buildfarmjob(date_created);
CREATE INDEX buildfarmjob__date_started__idx ON buildfarmjob(date_started);
CREATE INDEX buildfarmjob__date_finished__idx ON buildfarmjob(date_finished);
CREATE INDEX buildfarmjob__builder_and_status__idx
    ON buildfarmjob(builder, status);
CREATE INDEX buildfarmjob__log__idx ON buildfarmjob(log) WHERE log IS NOT NULL;


CREATE TABLE PackageBuild (
    id serial PRIMARY KEY,
    build_farm_job integer NOT NULL
        CONSTRAINT packagebuild__build_farm_job__fk REFERENCES buildfarmjob,
    archive integer NOT NULL
        CONSTRAINT packagebuild__archive__fk REFERENCES archive,
    pocket integer NOT NULL DEFAULT 0,
    upload_log integer
        CONSTRAINT packagebuild__log__fk REFERENCES libraryfilealias,
    dependencies text
);

INSERT INTO PackageBuild (
    id, build_farm_job, archive, pocket, upload_log, dependencies)
SELECT id, id AS build_farm_job, archive, pocket, upload_log, dependencies
FROM BuildInfo;
SELECT setval('packagebuild_id_seq', MAX(id)) FROM PackageBuild;

CREATE UNIQUE INDEX packagebuild__build_farm_job__idx ON packagebuild(
    build_farm_job);
CREATE INDEX packagebuild__archive__idx ON packagebuild(archive);
CREATE INDEX packagebuild__upload_log__idx ON packagebuild(upload_log)
    WHERE upload_log IS NOT NULL;

CREATE TABLE BinaryPackageBuild (
    id serial PRIMARY KEY,
    package_build integer NOT NULL
        CONSTRAINT binarypackagebuild__package_build__fk
        REFERENCES packagebuild,
    distro_arch_series integer NOT NULL
        CONSTRAINT binarypackagebuild__distro_arch_series__fk
        REFERENCES distroarchseries,
    source_package_release integer NOT NULL
        CONSTRAINT binarypackagebuild__source_package_release__fk
        REFERENCES sourcepackagerelease
);

INSERT INTO binarypackagebuild(
    id, package_build, distro_arch_series, source_package_release)
SELECT id, id, distro_arch_series, source_package_release
FROM BuildInfo;

SELECT setval('binarypackagebuild_id_seq', MAX(id)) FROM BinaryPackageBuild;

CREATE UNIQUE INDEX binarypackagebuild__package_build__idx
    ON binarypackagebuild(package_build);
-- Indexes that we can no longer create:
-- CREATE UNIQUE INDEX binarypackagebuild__distro_arch_series_uniq__idx ON binarypackagebuild(distro_arch_series, source_package_release, archive)
-- CREATE INDEX binarypackagebuild__distro_arch_series__status__idx ON binarypackagebuild(distro_arch_series, status?)
-- CREATE INDEX binarypackagebuild__distro_arch_series__date_finished ON binarypackagebuild(distro_arch_series, date_finished)
CREATE INDEX binarypackagebuild__source_package_release_idx
    ON binarypackagebuild(source_package_release);
CREATE INDEX binarypackagebuild__distro_arch_series__idx
    ON BinaryPackageBuild(distro_arch_series);

-- Step 3
-- Need to update all the references to the current build table to point to
-- the new table, shown by:
-- launchpad_dev=# select t.constraint_name, t.table_name, t.constraint_type,
-- launchpad_dev-# c.table_name, c.column_name
-- launchpad_dev-# from information_schema.table_constraints t,
-- launchpad_dev-# information_schema.constraint_column_usage c
-- launchpad_dev-# where t.constraint_name = c.constraint_name
-- launchpad_dev-# and t.constraint_type = 'FOREIGN KEY'
-- launchpad_dev-# and c.table_name = 'build'
-- launchpad_dev-# ;

-- "binarypackagerelease__build__fk" FOREIGN KEY (build) REFERENCES build(id) ON DELETE CASCADE
ALTER TABLE BinaryPackageRelease DROP CONSTRAINT binarypackagerelease__build__fk;
ALTER TABLE BinaryPackageRelease
 ADD CONSTRAINT binarypackagerelease_build_fk
 FOREIGN KEY (build) REFERENCES binarypackagebuild(id) ON DELETE CASCADE;

-- "buildpackagejob__build__fk" FOREIGN KEY (build) REFERENCES build(id)
ALTER TABLE BuildPackageJob DROP CONSTRAINT buildpackagejob__build__fk;
ALTER TABLE BuildPackageJob
 ADD CONSTRAINT buildpackagejob_build_fk
 FOREIGN KEY (build) REFERENCES binarypackagebuild(id);

-- "packageuploadbuild_build_fk" FOREIGN KEY (build) REFERENCES build(id)
ALTER TABLE packageuploadbuild DROP CONSTRAINT packageuploadbuild_build_fk;
ALTER TABLE packageuploadbuild
 ADD CONSTRAINT packageuploadbuild_build_fk
 FOREIGN KEY (build) REFERENCES binarypackagebuild(id);


-- "securebinarypackagepublishinghistory_supersededby_fk" FOREIGN KEY (supersededby) REFERENCES build(id)
ALTER TABLE binarypackagepublishinghistory
 DROP CONSTRAINT securebinarypackagepublishinghistory_supersededby_fk;
ALTER TABLE binarypackagepublishinghistory
 ADD CONSTRAINT binarypackagepublishinghistory_supersededby_fk
 FOREIGN KEY (supersededby) REFERENCES binarypackagebuild(id);


-- Step 4
-- Drop the old Build table and its constraints.
ALTER TABLE Build SET SCHEMA todrop;
ALTER TABLE todrop.Build DROP CONSTRAINT build__archive__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__builder__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__buildlog__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__distroarchseries__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__processor__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__sourcepackagerelease__fk;
ALTER TABLE todrop.Build DROP CONSTRAINT build__upload_log__fk;


-- Step 5
-- Update views that reference the build table:
CREATE OR REPLACE VIEW PublishedPackage AS
SELECT securebinarypackagepublishinghistory.id, distroarchseries.id AS distroarchseries, distroseries.distribution, distroseries.id AS distroseries, distroseries.name AS distroseriesname, processorfamily.id AS processorfamily, processorfamily.name AS processorfamilyname, securebinarypackagepublishinghistory.status AS packagepublishingstatus, component.name AS component, section.name AS section, binarypackagerelease.id AS binarypackagerelease, binarypackagename.name AS binarypackagename, binarypackagerelease.summary AS binarypackagesummary, binarypackagerelease.description AS binarypackagedescription, binarypackagerelease.version AS binarypackageversion, binarypackagebuild.id AS build, buildfarmjob.date_finished AS datebuilt, sourcepackagerelease.id AS sourcepackagerelease, sourcepackagerelease.version AS sourcepackagereleaseversion, sourcepackagename.name AS sourcepackagename, securebinarypackagepublishinghistory.pocket, securebinarypackagepublishinghistory.archive, binarypackagerelease.fti AS binarypackagefti
 FROM binarypackagepublishinghistory securebinarypackagepublishinghistory
 JOIN distroarchseries ON distroarchseries.id = securebinarypackagepublishinghistory.distroarchseries
 JOIN distroseries ON distroarchseries.distroseries = distroseries.id
 JOIN processorfamily ON distroarchseries.processorfamily = processorfamily.id
 JOIN component ON securebinarypackagepublishinghistory.component = component.id
 JOIN binarypackagerelease ON securebinarypackagepublishinghistory.binarypackagerelease = binarypackagerelease.id
 JOIN section ON securebinarypackagepublishinghistory.section = section.id
 JOIN binarypackagename ON binarypackagerelease.binarypackagename = binarypackagename.id
 JOIN binarypackagebuild ON binarypackagerelease.build = binarypackagebuild.id
 JOIN packagebuild ON binarypackagebuild.package_build = packagebuild.id
 JOIN buildfarmjob ON packagebuild.build_farm_job = buildfarmjob.id
 JOIN sourcepackagerelease ON binarypackagebuild.source_package_release = sourcepackagerelease.id
 JOIN sourcepackagename ON sourcepackagerelease.sourcepackagename = sourcepackagename.id
 WHERE securebinarypackagepublishinghistory.dateremoved IS NULL;

CREATE OR REPLACE VIEW BinaryPackageFilePublishing As
SELECT (libraryfilealias.id::text || '.'::text) || securebinarypackagepublishinghistory.id::text AS id, distroseries.distribution, securebinarypackagepublishinghistory.id AS binarypackagepublishing, component.name AS componentname, libraryfilealias.filename AS libraryfilealiasfilename, sourcepackagename.name AS sourcepackagename, binarypackagefile.libraryfile AS libraryfilealias, distroseries.name AS distroseriesname, distroarchseries.architecturetag, securebinarypackagepublishinghistory.status AS publishingstatus, securebinarypackagepublishinghistory.pocket, securebinarypackagepublishinghistory.archive
 FROM binarypackagepublishinghistory securebinarypackagepublishinghistory
 JOIN binarypackagerelease ON securebinarypackagepublishinghistory.binarypackagerelease = binarypackagerelease.id
 JOIN binarypackagebuild ON binarypackagerelease.build = binarypackagebuild.id
 JOIN sourcepackagerelease ON binarypackagebuild.source_package_release = sourcepackagerelease.id
 JOIN sourcepackagename ON sourcepackagerelease.sourcepackagename = sourcepackagename.id
 JOIN binarypackagefile ON binarypackagefile.binarypackagerelease = binarypackagerelease.id
 JOIN libraryfilealias ON binarypackagefile.libraryfile = libraryfilealias.id
 JOIN distroarchseries ON securebinarypackagepublishinghistory.distroarchseries = distroarchseries.id
 JOIN distroseries ON distroarchseries.distroseries = distroseries.id
 JOIN component ON securebinarypackagepublishinghistory.component = component.id
 WHERE securebinarypackagepublishinghistory.dateremoved IS NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 57, 0);
