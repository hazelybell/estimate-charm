SET client_min_messages=ERROR;

CREATE TABLE PublisherConfig (
    id serial PRIMARY KEY,
    distribution integer NOT NULL CONSTRAINT publisherconfig__distribution__fk REFERENCES distribution,
    root_dir text NOT NULL,
    base_url text NOT NULL,
    copy_base_url text NOT NULL
);
    
CREATE UNIQUE INDEX publisherconfig__distribution__idx
    ON PublisherConfig(distribution);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 52, 0);
