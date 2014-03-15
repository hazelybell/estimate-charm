SET client_min_messages TO ERROR;

UPDATE BugActivity SET person=(SELECT id FROM Person WHERE name='janitor')
FROM (
    SELECT BugActivity.id
    FROM BugActivity LEFT OUTER JOIN Person ON BugActivity.person = Person.id
    WHERE Person.id IS NULL
    ) AS Whatever
WHERE Whatever.id = BugActivity.id;

ALTER TABLE BugActivity
    ADD CONSTRAINT bugactivity__person__fk
    FOREIGN KEY (person) REFERENCES Person;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 0, 3);

