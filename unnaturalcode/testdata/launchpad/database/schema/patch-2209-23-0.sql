-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE SCHEMA trgm;
CREATE EXTENSION pg_trgm WITH SCHEMA trgm;

CREATE INDEX distributionsourcepackagecache__name__idx
    ON distributionsourcepackagecache USING gin (name trgm.gin_trgm_ops);
CREATE INDEX sourcepackagepublishinghistory__archive__distroseries__spn__status__idx
    ON sourcepackagepublishinghistory (archive, distroseries, sourcepackagename, status);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 23, 0);
