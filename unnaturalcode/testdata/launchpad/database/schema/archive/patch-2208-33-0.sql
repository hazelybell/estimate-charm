SET client_min_messages=ERROR;

CREATE TABLE SubunitStream (
    id           SERIAL PRIMARY KEY,
    uploader     INTEGER NOT NULL REFERENCES Person(id),
    date_created timestamp without time zone NOT NULL
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    branch       INTEGER NOT NULL REFERENCES Branch(id),
    stream       INTEGER NOT NULL REFERENCES LibraryFileAlias(id)
);

CREATE INDEX SubunitStream__uploader_created__idx ON SubunitStream(uploader, date_created);
CREATE INDEX SubunitStream__branch_created__idx ON SubunitStream(branch, date_created);
CREATE INDEX SubunitStream__stream__idx ON SubunitStream(stream);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 33, 0);
