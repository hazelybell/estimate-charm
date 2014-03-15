-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE BugSubscriptionFilterInformationType (
    filter integer REFERENCES BugSubscriptionFilter(id) NOT NULL,
    information_type integer NOT NULL,
    CONSTRAINT bugsubscriptioninformationtype_pkey PRIMARY KEY (filter, information_type));

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 26, 3);
