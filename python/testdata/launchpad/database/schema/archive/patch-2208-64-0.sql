-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE DistroSeriesDifference
    ADD COLUMN parent_series INTEGER
        CONSTRAINT distroseriesdifference__parentseries__fk REFERENCES distroseries;
-- Because of the likelihood of staging and production having existing data,
-- we need to set it, but only for Ubuntu.
UPDATE DistroSeriesDifference SET parent_series = (SELECT id from DistroSeries WHERE name = 'sid') FROM Distribution, DistroSeries WHERE Distribution.name = 'ubuntu' AND DistroSeries.id = derived_series AND DistroSeries.distribution = Distribution.id;
ALTER TABLE DistroSeriesDifference ALTER COLUMN parent_series SET NOT NULL;

CREATE INDEX distroseriesdifference__parent_series__idx ON DistroSeriesDifference(parent_series);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 64, 0);
