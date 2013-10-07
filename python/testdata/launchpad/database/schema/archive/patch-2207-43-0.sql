SET client_min_messages=ERROR;
ALTER TABLE sourcepackagerelease ADD changelog int REFERENCES libraryfilealias(id);
CREATE INDEX sourcepackagerelease__changelog__idx ON SourcepackageRelease(changelog);
INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 43, 0);
