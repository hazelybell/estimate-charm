SET client_min_messages=ERROR;

CREATE TABLE productjob (
    id SERIAL PRIMARY KEY,
    job integer NOT NULL REFERENCES job ON DELETE CASCADE,
    job_type integer NOT NULL,
    product integer NOT NULL REFERENCES product,
    json_data text
);

-- Queries will search for recent jobs of a specific type.
-- Maybe this is unproductive because there may never be more than 20 types.
CREATE INDEX productjob__job_type_idx
    ON productjob USING btree (job_type);


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 15, 1);
