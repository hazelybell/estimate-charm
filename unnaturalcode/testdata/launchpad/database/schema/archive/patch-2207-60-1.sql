SET client_min_messages=ERROR;

CREATE INDEX archive__require_virtualized__idx
ON Archive(require_virtualized);

CREATE INDEX buildfarmjob__status__idx
ON BuildFarmJob(status);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 60, 1);

