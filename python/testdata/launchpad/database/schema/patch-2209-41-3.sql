-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE INDEX buildfarmjob__archive__date_created__id__idx
    ON buildfarmjob (archive, date_created DESC, id)
    WHERE archive IS NOT NULL;
CREATE INDEX buildfarmjob__archive__status__date_created__id__idx
    ON buildfarmjob (archive, status, date_created DESC, id)
    WHERE archive IS NOT NULL;
CREATE INDEX buildfarmjob__archive__status__date_finished__id__idx
    ON buildfarmjob (archive, status, date_finished DESC, id)
    WHERE archive IS NOT NULL;


CREATE INDEX binarypackagebuild__status__id__idx
    ON binarypackagebuild (status, id);
CREATE INDEX binarypackagebuild__builder__status__date_finished__id__idx
    ON binarypackagebuild (builder, status, date_finished DESC, id)
    WHERE builder IS NOT NULL;

CREATE INDEX binarypackagebuild__archive__status__date_created__id__idx
    ON binarypackagebuild (archive, status, date_created DESC, id);
CREATE INDEX binarypackagebuild__archive__status__date_finished__id__idx
    ON binarypackagebuild (archive, status, date_finished DESC, id);

CREATE INDEX binarypackagebuild__das__status__date_finished__id__idx
    ON binarypackagebuild (distro_arch_series, status, date_finished DESC, id);
CREATE INDEX binarypackagebuild__das__status__id__idx
    ON binarypackagebuild (distro_arch_series, status, id);
CREATE INDEX binarypackagebuild__das__id__idx
    ON binarypackagebuild (distro_arch_series, id);

CREATE INDEX binarypackagebuild__spr__archive__status__idx
    ON binarypackagebuild (source_package_release, archive, status);
CREATE INDEX binarypackagebuild__spr__distro_arch_series__status__idx
    ON binarypackagebuild (source_package_release, distro_arch_series, status);


CREATE INDEX sourcepackagerecipebuild__recipe__date_created__idx
    ON sourcepackagerecipebuild (recipe, date_created DESC);
CREATE INDEX sourcepackagerecipebuild__recipe__started__finished__created__idx
    ON sourcepackagerecipebuild (
        recipe, GREATEST(date_started, date_finished) DESC, date_created DESC,
        id DESC);
CREATE INDEX sourcepackagerecipebuild__recipe__started__finished__idx
    ON sourcepackagerecipebuild (
        recipe, GREATEST(date_started, date_finished) DESC, id DESC);
CREATE INDEX sourcepackagerecipebuild__recipe__status__id__idx
    ON sourcepackagerecipebuild (recipe, status, id DESC);
CREATE INDEX sourcepackagerecipebuild__recipe__date_finished__idx
    ON sourcepackagerecipebuild (recipe, date_finished DESC);

CREATE INDEX binarypackagepublishinghistory__archive__bpr__status__idx
    ON binarypackagepublishinghistory (archive, binarypackagerelease, status);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 3);
