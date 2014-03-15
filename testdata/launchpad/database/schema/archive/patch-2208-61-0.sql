-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE DistroSeriesParent (
    id serial PRIMARY KEY,
    derived_series integer NOT NULL
        CONSTRAINT distroseriesparent__derivedseries__fk REFERENCES distroseries,
    parent_series integer NOT NULL
        CONSTRAINT distroseriesparent__parentseries__fk REFERENCES distroseries,
    initialized boolean NOT NULL
);

CREATE INDEX distroseriesparent__derivedseries__idx
    ON DistroSeriesParent (derived_series);
CREATE INDEX distroseriesparent__parentseries__idx
    ON DistroSeriesParent (parent_series);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 61, 0);
