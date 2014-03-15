SET client_min_messages=ERROR;

ALTER TABLE SourcePackagePublishingHistory
    ADD COLUMN ancestor INTEGER REFERENCES SourcePackagePublishingHistory;
CREATE INDEX sourcepackagepublishinghistory__ancestor__idx ON sourcepackagepublishinghistory(ancestor);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 34, 0);

