-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE LatestPersonSourcePackageReleaseCache (
    id serial PRIMARY KEY,
    publication integer NOT NULL REFERENCES sourcepackagepublishinghistory(id),
    date_uploaded timestamp without time zone NOT NULL,
    creator integer,
    maintainer integer,
    archive_purpose integer NOT NULL,
    upload_archive integer NOT NULL REFERENCES archive(id),
    upload_distroseries integer NOT NULL REFERENCES distroseries(id),
    sourcepackagename integer NOT NULL REFERENCES sourcepackagename(id),
    sourcepackagerelease integer NOT NULL REFERENCES sourcepackagerelease(id)
);


CREATE INDEX latestpersonsourcepackagereleasecache__creator__idx
    ON LatestPersonSourcePackageReleaseCache USING btree (creator) WHERE (creator IS NOT NULL);

CREATE INDEX latestpersonsourcepackagereleasecache__maintainer__idx
    ON LatestPersonSourcePackageReleaseCache USING btree (maintainer) WHERE (maintainer IS NOT NULL);

CREATE INDEX latestpersonsourcepackagereleasecache__archive_purpose__idx
    ON LatestPersonSourcePackageReleaseCache USING btree (archive_purpose);

ALTER TABLE LatestPersonSourcePackageReleaseCache ADD CONSTRAINT creator__upload_archive__upload_distroseries__sourcepackagename__key
     UNIQUE (creator, upload_archive, upload_distroseries, sourcepackagename);

ALTER TABLE LatestPersonSourcePackageReleaseCache ADD CONSTRAINT maintainer__upload_archive__upload_distroseries__sourcepackagename__key
     UNIQUE (maintainer, upload_archive, upload_distroseries, sourcepackagename);

COMMENT ON TABLE LatestPersonSourcePackageReleaseCache IS 'LatestPersonSourcePackageReleaseCache: The most recent published source package releases for a given (distroseries, archive, sourcepackage).';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.creator IS 'The creator of the source package release.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.maintainer IS 'The maintainer of the source package in the DSC.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.upload_archive IS 'The target archive for the release.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.sourcepackagename IS 'The SourcePackageName of the release.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.upload_distroseries IS 'The distroseries into which the sourcepackagerelease was published.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.sourcepackagerelease IS 'The sourcepackagerelease which was published.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.archive_purpose IS 'The purpose of the archive, e.g. COMMERCIAL.  See the ArchivePurpose DBSchema item.';
COMMENT ON COLUMN LatestPersonSourcePackageReleaseCache.date_uploaded IS 'The date/time on which the source was actually published into the archive.';


CREATE TABLE GarboJobState (
    name text PRIMARY KEY,
    json_data text
);

COMMENT ON TABLE GarboJobState IS 'Contains persistent state for named garbo jobs.';
COMMENT ON COLUMN GarboJobState.name IS 'The name of the job.';
COMMENT ON COLUMN GarboJobState.json_data IS 'A JSON struct containing data for the job.';


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 38, 0);
