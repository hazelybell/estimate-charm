
SET client_min_messages=ERROR;

DROP VIEW SourcePackagePublishingHistory;
DROP VIEW BinaryPackagePublishingHistory;

ALTER TABLE SecureSourcePackagePublishingHistory
    RENAME TO SourcePackagePublishingHistory;
ALTER TABLE SecureBinaryPackagePublishingHistory
    RENAME TO BinaryPackagePublishingHistory;

ALTER SEQUENCE securesourcepackagepublishinghistory_id_seq
    RENAME TO sourcepackagepublishinghistory_id_seq;
ALTER SEQUENCE securebinarypackagepublishinghistory_id_seq
    RENAME TO binarypackagepublishinghistory_id_seq;

ALTER TABLE SourcePackagePublishingHistory
    DROP COLUMN embargolifted;
ALTER TABLE SourcePackagePublishingHistory
    DROP COLUMN embargo;
ALTER TABLE BinaryPackagePublishingHistory
    DROP COLUMN embargolifted;
ALTER TABLE BinaryPackagePublishingHistory
    DROP COLUMN embargo;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 31, 0);

