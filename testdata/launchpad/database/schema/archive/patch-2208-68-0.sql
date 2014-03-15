-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE PackageCopyJob (
    id serial PRIMARY KEY,
    job integer NOT NULL CONSTRAINT packagecopyjob__job__fk REFERENCES job,
    source_archive integer NOT NULL REFERENCES Archive,
    target_archive integer NOT NULL REFERENCES Archive,
    target_distroseries integer REFERENCES DistroSeries,
    job_type integer NOT NULL,
    json_data text
);

ALTER TABLE PackageCopyJob
  ADD CONSTRAINT packagecopyjob__job__key UNIQUE (job);
CREATE INDEX packagecopyjob__source
  ON PackageCopyJob (source_archive);
CREATE INDEX packagecopyjob__target
  ON PackageCopyJob (target_archive, target_distroseries);

ALTER TABLE PackageUpload
  ADD COLUMN package_copy_job integer
    CONSTRAINT packageupload__package_copy_job__fk REFERENCES PackageCopyJob;
CREATE INDEX packageupload__package_copy_job__idx
  ON PackageUpload(package_copy_job)
    WHERE package_copy_job IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 68, 0);
