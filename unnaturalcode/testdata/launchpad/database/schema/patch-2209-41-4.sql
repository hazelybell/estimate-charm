-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Distribution:+builds
CREATE INDEX binarypackagebuild__distro__status__date_finished__id__idx
    ON binarypackagebuild (distribution, status, date_finished DESC, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__distro__status__id__idx
    ON binarypackagebuild (distribution, status, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__distro__id__idx
    ON binarypackagebuild (distribution, id)
    WHERE is_distro_archive;

-- DistroSeries:+builds
CREATE INDEX binarypackagebuild__ds__status__date_finished__id__idx
    ON binarypackagebuild (distro_series, status, date_finished DESC, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__ds__status__id__idx
    ON binarypackagebuild (distro_series, status, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__ds__id__idx
    ON binarypackagebuild (distro_series, id)
    WHERE is_distro_archive;

-- DistroArchSeries:+builds
CREATE INDEX binarypackagebuild__das__status__date_finished__id__2__idx
    ON binarypackagebuild (distro_arch_series, status, date_finished DESC, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__das__status__id__2__idx
    ON binarypackagebuild (distro_arch_series, status, id)
    WHERE is_distro_archive;
CREATE INDEX binarypackagebuild__das__id__2__idx
    ON binarypackagebuild (distro_arch_series, id)
    WHERE is_distro_archive;

-- BinaryPackageBuild.estimateDuration, and general (archive, DAS) queries.
CREATE INDEX binarypackagebuild__archive__das__spn__status__finished__idx
    ON binarypackagebuild (archive, distro_arch_series, source_package_name,
                           status, date_finished, id);

-- General queries by SPN.
CREATE INDEX binarypackagebuild__source_package_name__idx
    ON binarypackagebuild (source_package_name);

-- And grabbing BPRs/SPRs by (name, version).
CREATE INDEX binarypackagerelease__binarypackagename__version__idx
    ON binarypackagerelease (binarypackagename, version);
CREATE INDEX sourcepackagerelease__sourcepackagename__version__idx
    ON sourcepackagerelease (sourcepackagename, version);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 41, 4);
