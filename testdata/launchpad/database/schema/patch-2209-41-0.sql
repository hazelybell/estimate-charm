-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE binarypackagebuild
    ADD COLUMN archive integer REFERENCES archive,
    ADD COLUMN pocket integer,
    ADD COLUMN processor integer REFERENCES processor,
    ADD COLUMN virtualized boolean,
    ADD COLUMN date_created timestamp without time zone,
    ADD COLUMN date_started timestamp without time zone,
    ADD COLUMN date_finished timestamp without time zone,
    ADD COLUMN date_first_dispatched timestamp without time zone,
    ADD COLUMN builder integer REFERENCES builder,
    ADD COLUMN status integer,
    ADD COLUMN log integer REFERENCES libraryfilealias,
    ADD COLUMN upload_log integer REFERENCES libraryfilealias,
    ADD COLUMN dependencies text,
    ADD COLUMN failure_count integer,
    ADD COLUMN build_farm_job integer REFERENCES buildfarmjob,
    ADD COLUMN distribution integer REFERENCES distribution,
    ADD COLUMN distro_series integer REFERENCES distroseries,
    ADD COLUMN is_distro_archive boolean,
    ADD COLUMN source_package_name integer REFERENCES sourcepackagename,
    ALTER COLUMN package_build DROP NOT NULL;
ALTER TABLE binarypackagebuild
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    ALTER COLUMN failure_count SET DEFAULT 0;

ALTER TABLE sourcepackagerecipebuild
    ADD COLUMN archive integer REFERENCES archive,
    ADD COLUMN pocket integer,
    ADD COLUMN processor integer REFERENCES processor,
    ADD COLUMN virtualized boolean,
    ADD COLUMN date_created timestamp without time zone,
    ADD COLUMN date_started timestamp without time zone,
    ADD COLUMN date_finished timestamp without time zone,
    ADD COLUMN date_first_dispatched timestamp without time zone,
    ADD COLUMN builder integer REFERENCES builder,
    ADD COLUMN status integer,
    ADD COLUMN log integer REFERENCES libraryfilealias,
    ADD COLUMN upload_log integer REFERENCES libraryfilealias,
    ADD COLUMN dependencies text,
    ADD COLUMN failure_count integer,
    ADD COLUMN build_farm_job integer REFERENCES buildfarmjob,
    ALTER COLUMN package_build DROP NOT NULL;
ALTER TABLE sourcepackagerecipebuild
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    ALTER COLUMN failure_count SET DEFAULT 0;

ALTER TABLE translationtemplatesbuild
    ADD COLUMN processor integer REFERENCES processor,
    ADD COLUMN virtualized boolean,
    ADD COLUMN date_created timestamp without time zone,
    ADD COLUMN date_started timestamp without time zone,
    ADD COLUMN date_finished timestamp without time zone,
    ADD COLUMN date_first_dispatched timestamp without time zone,
    ADD COLUMN builder integer REFERENCES builder,
    ADD COLUMN status integer,
    ADD COLUMN log integer REFERENCES libraryfilealias,
    ADD COLUMN failure_count integer;
ALTER TABLE sourcepackagerecipebuild
    ALTER COLUMN date_created
        SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    ALTER COLUMN failure_count SET DEFAULT 0;

-- BuildFarmJob is becoming a shadow of its former self, so more columns
-- have to be nullable, but it also grows an archive column to hasten
-- access checks.
ALTER TABLE buildfarmjob
    ADD COLUMN archive integer REFERENCES archive,
    ALTER COLUMN failure_count DROP NOT NULL,
    DROP CONSTRAINT started_if_finished;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 0);
