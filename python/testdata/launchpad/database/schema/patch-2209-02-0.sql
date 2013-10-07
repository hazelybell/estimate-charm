-- Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

-- Add a new sponsor column to SPPH.
-- We deliberately leave it Null for existing records.
ALTER TABLE SourcePackagePublishingHistory
    ADD COLUMN sponsor INTEGER
        CONSTRAINT sourcepackagepublishinghistory__sponsor__fk
            REFERENCES Person;

-- We create a partial index because:
-- - we are only interested in non-null sponsors;
-- - the index creation needs to be quick (spph has ~1.6M rows atm).
CREATE INDEX sourcepackagepublishinghistory__sponsor__idx
    ON SourcePackagePublishingHistory(sponsor)
        WHERE sponsor IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 02, 0);
