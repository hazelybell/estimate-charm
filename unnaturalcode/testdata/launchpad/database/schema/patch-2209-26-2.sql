-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE bugsubscriptionfilterstatus DROP COLUMN id;
DROP INDEX bugsubscriptionfilterstatus__filter__status__idx;
ALTER TABLE bugsubscriptionfilterstatus ADD CONSTRAINT bugsubscriptionfilterstatus_pkey PRIMARY KEY (filter, status);

ALTER TABLE bugsubscriptionfilterimportance DROP COLUMN id;
DROP INDEX bugsubscriptionfilterimportance__filter__importance__idx;
ALTER TABLE bugsubscriptionfilterimportance ADD CONSTRAINT bugsubscriptionfilterimportance_pkey PRIMARY KEY (filter, importance);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 26, 2);
