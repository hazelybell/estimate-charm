-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Thanks to our feature flags, this table should be empty.  If not,
-- adding a NOT NULL column would be problematic!
ALTER TABLE PackageCopyJob ADD COLUMN package_name text NOT NULL;

ALTER TABLE PackageCopyJob ADD COLUMN copy_policy integer;

-- For getPendingJobsForTargetSeries, which happens on web-request time.
CREATE UNIQUE INDEX packagecopyjob__job_type__target_ds__id__key
    ON PackageCopyJob(job_type, target_distroseries, id);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 73, 0);
