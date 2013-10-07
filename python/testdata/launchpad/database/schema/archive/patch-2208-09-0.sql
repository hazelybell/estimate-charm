-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE BugTrackerComponentGroup (
    id serial PRIMARY KEY,
    name text NOT NULL,
    bug_tracker integer NOT NULL REFERENCES BugTracker,

    CONSTRAINT valid_name CHECK (valid_name(name))
);

ALTER TABLE BugTrackerComponentGroup
    ADD CONSTRAINT bugtrackercomponentgroup__bug_tracker__name__key
    UNIQUE (bug_tracker, name);


CREATE TABLE BugTrackerComponent (
    id serial PRIMARY KEY,
    name text NOT NULL,
    is_visible boolean NOT NULL DEFAULT True,
    is_custom boolean NOT NULL DEFAULT True,
    component_group integer NOT NULL REFERENCES BugTrackerComponentGroup,
    distro_source_package integer REFERENCES DistributionSourcePackage,

    CONSTRAINT valid_name CHECK (valid_name(name))
);

ALTER TABLE BugTrackerComponent
    ADD CONSTRAINT bugtrackercomponent__component_group__name__key
    UNIQUE (component_group, name);

ALTER TABLE BugTrackerComponent
    ADD CONSTRAINT bugtrackercomponent__distro_source_package__key
    UNIQUE (distro_source_package);

INSERT INTO LaunchpadDatabaseRevision VALUES(2208, 09, 0);
