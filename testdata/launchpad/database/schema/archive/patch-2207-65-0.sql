SET client_min_messages=ERROR;

ALTER TABLE BuildQueue ADD CONSTRAINT buildqueue__processor__fk
    FOREIGN KEY (processor) REFERENCES Processor;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 65, 0);

