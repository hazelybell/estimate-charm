SET client_min_messages=ERROR;

CREATE INDEX hwsubmissiondevice__parent__idx ON HWSubmissionDevice(parent);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 18, 0);
