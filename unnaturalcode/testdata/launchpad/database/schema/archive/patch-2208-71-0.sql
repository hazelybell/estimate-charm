-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Add a column to identifie a DSP as an overlay.
ALTER TABLE DistroSeriesParent
    ADD COLUMN is_overlay BOOLEAN NOT NULL DEFAULT FALSE;

-- Add a reference to a component.
ALTER TABLE DistroSeriesParent
    ADD COLUMN component INTEGER REFERENCES Component;

-- Add a 'reference' to a pocket.
ALTER TABLE DistroSeriesParent
    ADD COLUMN pocket INTEGER;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 71, 0);
