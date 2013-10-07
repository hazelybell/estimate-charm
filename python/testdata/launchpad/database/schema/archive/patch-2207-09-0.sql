SET client_min_messages=ERROR;

-- Per Bug #196774
ALTER TABLE Packaging
    DROP CONSTRAINT packaging_uniqueness,
    ADD CONSTRAINT packaging__distroseries__sourcepackagename__key
        UNIQUE (distroseries, sourcepackagename);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 9, 0);

