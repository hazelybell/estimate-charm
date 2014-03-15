SET client_min_messages=ERROR;

/* PersonTransferJob can handle jobs adding a member to a team
 * or merging to person objects.
 */
CREATE TABLE PersonTransferJob (
    id           SERIAL PRIMARY KEY,
    job          INTEGER NOT NULL UNIQUE REFERENCES Job(id),
    job_type     INTEGER NOT NULL,
    minor_person INTEGER NOT NULL REFERENCES Person(id),
    major_person INTEGER NOT NULL REFERENCES Person(id),
    json_data    text
);

CREATE TABLE QuestionJob (
    id        SERIAL PRIMARY KEY,
    job       INTEGER NOT NULL UNIQUE REFERENCES Job(id),
    job_type  INTEGER NOT NULL,
    question  INTEGER NOT NULL REFERENCES Question(id),
    json_data text
);

CREATE INDEX PersonTransferJob__minor_person__idx ON PersonTransferJob(minor_person);
CREATE INDEX PersonTransferJob__major_person__idx ON PersonTransferJob(major_person);
CREATE INDEX QuestionJob__question__idx ON QuestionJob(question);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 25, 0);
