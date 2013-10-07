-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE milestonetag (
    id SERIAL PRIMARY KEY,
    milestone integer NOT NULL REFERENCES milestone ON DELETE CASCADE,
    tag text NOT NULL,
    date_created timestamp without time zone DEFAULT
        timezone('UTC'::text, now()) NOT NULL,
    created_by integer NOT NULL REFERENCES person,
    CONSTRAINT valid_tag CHECK (valid_name(tag))
);

ALTER TABLE ONLY milestonetag
    ADD CONSTRAINT milestonetag__tag__milestone__key UNIQUE (tag, milestone);

CREATE INDEX milestonetag__milestones_idx
    ON milestonetag USING btree (milestone);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 0, 3);
