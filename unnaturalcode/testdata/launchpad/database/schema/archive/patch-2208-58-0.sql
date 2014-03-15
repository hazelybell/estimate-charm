-- Copyright 2011 Canonical Ltd. This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- A table to store subscription mutes in.

CREATE TABLE BugSubscriptionFilterMute (
    person integer REFERENCES Person(id)
        ON DELETE CASCADE NOT NULL,
    filter integer REFERENCES BugSubscriptionFilter(id)
        ON DELETE CASCADE NOT NULL,
    date_created timestamp without time zone
        DEFAULT timezone('UTC'::text, now()) NOT NULL,
    CONSTRAINT bugsubscriptionfiltermute_pkey PRIMARY KEY (person, filter)
);

-- We don't need an index on person, as the primary key index can be used
-- for those lookups. We have an index on just filter, as the bulk of our
-- lookups will be on filter.
CREATE INDEX bugsubscriptionfiltermute__filter__idx
    ON BugSubscriptionFilterMute(filter);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 58, 0);

