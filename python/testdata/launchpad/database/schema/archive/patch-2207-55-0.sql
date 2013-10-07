SET client_min_messages=ERROR;

ALTER TABLE Distribution
ADD COLUMN bug_reported_acknowledgement TEXT;

ALTER TABLE DistributionSourcePackage
ADD COLUMN bug_reported_acknowledgement TEXT;

ALTER TABLE Product
ADD COLUMN bug_reported_acknowledgement TEXT;

ALTER TABLE Project
ADD COLUMN bug_reported_acknowledgement TEXT;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 55, 0);

