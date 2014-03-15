-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- The `InitializeDistroSeriesJob` table captures the data required for an ifp job.

CREATE TABLE DistributionJob (
    id serial PRIMARY KEY,
    -- FK to the `Job` record with the "generic" data about this archive
    -- job.
    job integer NOT NULL CONSTRAINT distributionjob__job__fk REFERENCES job,
    -- FK to the associated `Distribution` record.
    distribution integer NOT NULL REFERENCES Distribution,
    distroseries integer REFERENCES DistroSeries,
    -- The particular type of foo job
    job_type integer NOT NULL,
    -- JSON data for use by the job
    json_data text
);

ALTER TABLE DistributionJob ADD CONSTRAINT distributionjob__job__key UNIQUE (job);
CREATE UNIQUE INDEX distribution_job__initialise_series__distroseries ON DistributionJob (distroseries) WHERE job_type = 1;
INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 10, 0);

