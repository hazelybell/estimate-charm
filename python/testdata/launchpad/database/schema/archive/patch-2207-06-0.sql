-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- ** PART 1 ** Create the 'packagesetgroup' table and the
--              'packageset.packagesetgroup' foreign key,
--              populate the 'packagesetgroup' table

-- This table keeps track of package sets that are equivalent across
-- distro series boundaries.
CREATE SEQUENCE packagesetgroup_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    NO MINVALUE
    CACHE 1;
CREATE TABLE packagesetgroup (
    id integer NOT NULL DEFAULT nextval('packagesetgroup_id_seq'),
    date_created timestamp without time zone DEFAULT timezone('UTC'::text, now()) NOT NULL,
    owner integer NOT NULL,
    -- Please note: the 'name' column is only here to ease the data migration
    -- and will be dropped at the end of this patch.
    name text NOT NULL
);
ALTER SEQUENCE packagesetgroup_id_seq OWNED BY packagesetgroup.id;
ALTER TABLE ONLY packagesetgroup
    ADD CONSTRAINT packagesetgroup_pkey PRIMARY KEY (id);
ALTER TABLE ONLY packagesetgroup
    ADD CONSTRAINT packagesetgroup__owner__fk
    FOREIGN KEY (owner) REFERENCES person(id);

-- Package sets and their clones belong to the same package set group.
ALTER TABLE ONLY packageset ADD COLUMN packagesetgroup integer;
ALTER TABLE ONLY packageset
  ADD CONSTRAINT packageset__packagesetgroup__fk
  FOREIGN KEY (packagesetgroup) REFERENCES packagesetgroup(id);

-- Create a group for each of the original (karmic koala) package sets.
INSERT INTO packagesetgroup(owner, name)
SELECT packageset.owner, packageset.name
FROM packageset WHERE NOT packageset.name LIKE('lucid-%');


-- ** PART 2 ** Associate the karmic koala package sets and their lucid lynx
--              clones with the appropriate package set groups

-- Update the karmic koala package sets so they reference their groups.
UPDATE packageset SET packagesetgroup = packagesetgroup.id
FROM packagesetgroup WHERE packageset.name = packagesetgroup.name;

-- Update the lucid lynx package set *clones* so they reference their groups
-- as well.
UPDATE packageset SET packagesetgroup = packagesetgroup.id
FROM packagesetgroup WHERE packageset.name = 'lucid-' || packagesetgroup.name;

-- ** PART 3 ** Add the 'packageset.distroseries' foreign key and
--              initialize it for the existing package sets.

-- A package set lives in a distro series context.
ALTER TABLE ONLY packageset ADD COLUMN distroseries integer;

-- Define the foreign key constraint.
ALTER TABLE ONLY packageset
  ADD CONSTRAINT packageset__distroseries__fk
  FOREIGN KEY (distroseries) REFERENCES distroseries(id);

-- First migrate the original package sets created for the karmic koala.
UPDATE packageset SET distroseries = distroseries.id FROM distroseries
WHERE distroseries.name = 'karmic' AND NOT packageset.name LIKE('lucid-%');

-- Migrate the lucid lynx package sets next.
UPDATE packageset SET distroseries = distroseries.id FROM distroseries
WHERE distroseries.name = 'lucid' AND packageset.name LIKE('lucid-%');

-- Make the 'distroseries' foreign key mandatory.
ALTER TABLE ONLY packageset ALTER COLUMN distroseries SET NOT NULL;

-- The package set name is now only unique in conjunction with a distro series.
ALTER TABLE ONLY packageset
    DROP CONSTRAINT packageset_name_key;
ALTER TABLE ONLY packageset
    ADD CONSTRAINT packageset__name__distroseries__key UNIQUE (name, distroseries);

-- ** PART 4 ** Strip off the 'lucid-' prefix of the lucid lynx
--              package set names
UPDATE packageset SET name = substring(name FROM length('lucid-')+1)
WHERE name LIKE('lucid-%');

-- ** PART 5 ** Create package set groups for package sets that were added in
--              lucid lynx but do not exist in the karmic koala,
--              associate these package sets with their newly created groups
INSERT INTO packagesetgroup(owner, name)
SELECT packageset.owner, packageset.name
FROM packageset, distroseries WHERE
    packageset.packagesetgroup IS NULL
    AND packageset.distroseries = distroseries.id
    AND distroseries.name = 'lucid';

UPDATE packageset SET packagesetgroup = packagesetgroup.id
FROM packagesetgroup, distroseries
WHERE
    packageset.packagesetgroup IS NULL
    AND packageset.distroseries = distroseries.id
    AND distroseries.name = 'lucid'
    AND packageset.name = packagesetgroup.name;

-- ** PART 6 ** Make the 'packageset.packagesetgroup' foreign key mandatory
ALTER TABLE ONLY packageset ALTER COLUMN packagesetgroup SET NOT NULL;

-- ** PART 7 ** Drop the 'packagesetgroup.name' column that was only added
--              for data migration purposes.
ALTER TABLE ONLY packagesetgroup DROP COLUMN name;

-- Define indices on the newly added foreign keys.
CREATE INDEX packageset__packagesetgroup__idx
    ON packageset(packagesetgroup);
CREATE INDEX packageset__distroseries__idx
    ON packageset(distroseries);
CREATE INDEX packagesetgroup__owner__idx ON PackageSetGroup(owner);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 06, 0);
