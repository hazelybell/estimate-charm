SET client_min_messages=ERROR;

-- Lower gathered statistics on this column to work around extreme planning
-- times issue being investigated.
ALTER TABLE TeamMembership ALTER person SET STATISTICS 100;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 00, 7);
