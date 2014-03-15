-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE sharingjob (
    id serial PRIMARY KEY,
    job integer REFERENCES Job ON DELETE CASCADE UNIQUE NOT NULL,
    product integer REFERENCES Product,
    distro integer REFERENCES Distribution,
    grantee integer REFERENCES Person,
    job_type integer NOT NULL,
    json_data text
);


COMMENT ON TABLE sharingjob IS 'Contains references to jobs that are executed for sharing.';

COMMENT ON COLUMN sharingjob.job IS 'A reference to a row in the Job table that has all the common job details.';

COMMENT ON COLUMN sharingjob.product IS 'The product that this job is for.';

COMMENT ON COLUMN sharingjob.distro IS 'The distro that this job is for.';

COMMENT ON COLUMN sharingjob.grantee IS 'The grantee that this job is for.';

COMMENT ON COLUMN sharingjob.job_type IS 'The type of job, like remove subscriptions, email users.';

COMMENT ON COLUMN sharingjob.json_data IS 'Data that is specific to the type of job.';

CREATE INDEX sharingjob__grantee__idx ON SharingJob(grantee);


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 17, 0);
