SET client_min_messages=ERROR;

-- This DB patch will be applied before rollout, and the tables added
-- to their replication set.

CREATE TABLE lp_TeamParticipation
AS SELECT * FROM TeamParticipation WHERE FALSE;
ALTER TABLE lp_TeamParticipation
    ADD CONSTRAINT lp_TeamParticipation_pkey PRIMARY KEY (id),
    ADD CONSTRAINT lp_TeamPerticipation__team__person__key
        UNIQUE (team, person);
CREATE INDEX lp_TeamParticipation__person__idx ON lp_TeamParticipation(person);


CREATE TABLE lp_PersonLocation AS SELECT * FROM PersonLocation WHERE FALSE;
ALTER TABLE lp_PersonLocation
    ADD CONSTRAINT lp_PersonLocation_pkey PRIMARY KEY (id),
    ADD CONSTRAINT lp_PersonLocation__person__key UNIQUE (person);


CREATE TABLE lp_Person AS SELECT * FROM Person WHERE FALSE;
ALTER TABLE lp_Person
    ADD CONSTRAINT lp_Person_pkey PRIMARY KEY (id),
    ADD CONSTRAINT lp_Person__name__key UNIQUE (name),
    ADD CONSTRAINT lp_Person__account__key UNIQUE (account);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 15, 1);

