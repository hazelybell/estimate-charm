SET client_min_messages=ERROR;

DROP INDEX specificationmessage__specification__message__idx;

ALTER TABLE SpecificationMessage
    ADD COLUMN visible boolean DEFAULT TRUE NOT NULL,
    ADD CONSTRAINT specificationmessage__specification__message__key
        UNIQUE (specification, message);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 01, 0);
