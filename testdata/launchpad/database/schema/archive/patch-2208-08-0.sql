-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE BugSubscriptionFilter (
    id serial PRIMARY KEY,
    structuralsubscription integer REFERENCES StructuralSubscription(id),
    find_all_tags boolean NOT NULL,
    include_any_tags boolean NOT NULL,
    exclude_any_tags boolean NOT NULL,
    other_parameters text,
    description text
);

CREATE INDEX bugsubscriptionfilter__structuralsubscription
    ON BugSubscriptionFilter(structuralsubscription);

CREATE TABLE BugSubscriptionFilterStatus (
    id serial PRIMARY KEY,
    filter integer REFERENCES BugSubscriptionFilter(id) NOT NULL,
    status integer NOT NULL);

CREATE INDEX bugsubscriptionfilterstatus__filter__status__idx
    ON BugSubscriptionFilterStatus(filter, status);

CREATE TABLE BugSubscriptionFilterImportance (
    id serial PRIMARY KEY,
    filter integer REFERENCES BugSubscriptionFilter(id) NOT NULL,
    importance integer NOT NULL);

CREATE INDEX bugsubscriptionfilterimportance__filter__importance__idx
    ON BugSubscriptionFilterImportance(filter, importance);

CREATE TABLE BugSubscriptionFilterTag (
    id serial PRIMARY KEY,
    filter integer REFERENCES BugSubscriptionFilter(id) NOT NULL,
    tag text NOT NULL,
    include boolean NOT NULL);

CREATE INDEX bugsubscriptionfiltertag__filter__tag__idx
    ON BugSubscriptionFilterTag(filter, tag);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 08, 0);
