SET client_min_messages=ERROR;

CREATE TABLE BugJob(
    id serial NOT NULL PRIMARY KEY,
    job integer NOT NULL REFERENCES Job(id),
    bug integer NOT NULL REFERENCES Bug(id),
    job_type integer NOT NULL,
    json_data text
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 28, 0)
