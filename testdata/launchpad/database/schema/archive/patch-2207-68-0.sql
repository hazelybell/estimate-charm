-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

-- database changes for https://dev.launchpad.net/LEP/FeatureFlags
SET client_min_messages=ERROR;

-- All flags set within various scopes
CREATE TABLE FeatureFlag (
    scope text not null,
    priority integer not null,
    flag text not null,
    value text,
    date_modified timestamp without time zone not null 
    	default (current_timestamp at time zone 'utc'),
    constraint feature_flag_pkey primary key (scope, flag),
    constraint feature_flag_unique_priority_per_flag unique (flag, priority)
);

insert into LaunchpadDatabaseRevision values (2207, 68, 0);


-- vim: sw=4
