-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Renaming owner to registrant for DistroSeries

-- Rename owner into registrant.
ALTER TABLE distroseries 
    RENAME COLUMN owner TO registrant;

-- 'Rename' constraint.
ALTER TABLE distroseries 
    ADD CONSTRAINT distroseries__registrant__fk 
    FOREIGN KEY (registrant) REFERENCES Person(id);
ALTER TABLE distroseries
    DROP CONSTRAINT distroseries__owner__fk;

-- Rename index.
ALTER INDEX distroseries__owner__idx 
    RENAME TO distroseries__registrant__idx;

-- Rename old misnamed indexes.
-- Don't rename primary key indexes though, as this causes Slony-I to explode.
--ALTER INDEX distrorelease_pkey
--    RENAME TO distroseries_pkey;
ALTER INDEX distrorelease_distribution_key
    RENAME TO distrorelease__distribution__name__key;
ALTER INDEX distrorelease_distro_release_unique
    RENAME TO distroseries__distribution__id__key;


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 56, 0);
