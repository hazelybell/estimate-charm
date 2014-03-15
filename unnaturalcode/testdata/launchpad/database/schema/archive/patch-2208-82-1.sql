-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- Add a new creator column to SPPH.
-- We deliberately leave it Null for existing records.
ALTER TABLE SourcePackagePublishingHistory
    ADD COLUMN creator INTEGER
        CONSTRAINT sourcepackagepublishinghistory__creator__fk
            REFERENCES Person;

-- We create a partial index because:
-- - we are only interested in non-null creators;
-- - the index creation needs to be quick (spph has ~1.6M rows atm).
CREATE INDEX sourcepackagepublishinghistory__creator__idx
    ON SourcePackagePublishingHistory(creator)
        WHERE creator is not Null;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 82, 1);
