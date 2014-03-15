-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE BugTrackerComponent
    ADD COLUMN distribution integer REFERENCES Distribution;

ALTER TABLE BugTrackerComponent
    ADD COLUMN source_package_name integer REFERENCES SourcePackageName;

ALTER TABLE BugTrackerComponent
    DROP CONSTRAINT bugtrackercomponent__distro_source_package__key;

ALTER TABLE BugTrackerComponent
    DROP COLUMN distro_source_package;

ALTER TABLE BugTrackerComponent ADD CONSTRAINT bugtrackercomponent__disto__spn__key
    UNIQUE (distribution, source_package_name);

ALTER TABLE BugTrackerComponent ADD CONSTRAINT valid_target
    CHECK (distribution IS NULL = source_package_name IS NULL);

INSERT INTO LaunchpadDatabaseRevision VALUES(2208, 19, 0);
