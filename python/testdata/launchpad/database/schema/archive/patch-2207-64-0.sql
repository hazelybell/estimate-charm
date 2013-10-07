-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- The schema patch required for adding archive jobs, the first being
-- creation of copy archives.

-- The `ArchiveJob` table captures the data required for an archive job.

CREATE TABLE ArchiveJob (
    id serial PRIMARY KEY,
    -- FK to the `Job` record with the "generic" data about this archive
    -- job.
    job integer NOT NULL CONSTRAINT archivejob__job__fk REFERENCES job ON DELETE CASCADE,
    -- FK to the associated `Archive` record.
    archive integer NOT NULL CONSTRAINT archivejob__archive__fk REFERENCES archive,
    -- The particular type of archive job
    job_type integer NOT NULL,
    -- JSON data for use by the job
    json_data text
);

ALTER TABLE ArchiveJob ADD CONSTRAINT archivejob__job__key UNIQUE (job);
CREATE INDEX archivejob__archive__job_type__idx ON ArchiveJob(archive, job_type);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 64, 0);
