SET client_min_messages=ERROR;

-- Add column to store the base_version for derived/parent versions.
ALTER TABLE DistroSeriesDifference ADD COLUMN base_version text;
ALTER TABLE DistroSeriesDifference ADD CONSTRAINT valid_base_version CHECK(valid_debian_version(base_version));

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 24, 0);
