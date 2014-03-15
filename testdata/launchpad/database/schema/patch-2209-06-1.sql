-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE TABLE specificationworkitem (
    id SERIAL PRIMARY KEY,
    title text NOT NULL,
    specification integer NOT NULL REFERENCES specification,
    assignee integer REFERENCES person,
    milestone integer REFERENCES milestone,
    date_created timestamp without time zone DEFAULT 
        timezone('UTC'::text, now()) NOT NULL,
    status integer NOT NULL,
    sequence integer NOT NULL,
    deleted boolean NOT NULL DEFAULT FALSE);

CREATE TABLE specificationworkitemchange (
    id SERIAL PRIMARY KEY,
    work_item integer NOT NULL REFERENCES specificationworkitem,
    new_status integer NOT NULL,
    new_milestone integer REFERENCES milestone,
    new_assignee integer REFERENCES person,
    date_created timestamp without time zone DEFAULT 
        timezone('UTC'::text, now()) NOT NULL);

CREATE TABLE specificationworkitemstats (
    id SERIAL PRIMARY KEY,
    specification integer REFERENCES specification,
    day date NOT NULL,
    status integer NOT NULL,
    assignee integer REFERENCES person,
    milestone integer REFERENCES milestone,
    count integer NOT NULL);

-- Foreign key, selecting by specification and sorting by sequence.
CREATE INDEX specificationworkitem__specification__sequence__idx
   ON SpecificationWorkItem(specification, sequence);

-- Foreign key.
CREATE INDEX specificationworkitem__milestone__idx
    ON SpecificationWorkItem(milestone);

-- Foreign key, required for person merge.
CREATE INDEX specificationworkitem__assignee__idx
    ON SpecificationWorkItem(assignee) WHERE assignee IS NOT NULL;

-- Foreign key, selecting by work_item and ordering by date_created
CREATE INDEX specificationworkitemchange__work_item__date_created__idx
    ON SpecificationWorkItemChange(work_item, date_created);

-- Foreign key.
CREATE INDEX specificationworkitemchange__new_milestone__idx
    ON SpecificationWorkItemChange(new_milestone)
        WHERE new_milestone IS NOT NULL;

-- Foreign key, required for person merge.
CREATE INDEX specificationworkitemchange__new_assignee__idx
    ON SpecificationWorkItemChange(new_assignee) WHERE new_assignee IS NOT NULL;

-- Foreign key, and selection by date.
CREATE INDEX specificationworkitemstats_specification__day__idx
    ON SpecificationWorkItemStats(specification, day);

-- Foreign key, required for person merge.
CREATE INDEX specificationworkitemstats__assignee__idx
    ON SpecificationWorkItemStats(assignee) WHERE assignee IS NOT NULL;

-- Foreign key.
CREATE INDEX specificationworkitemstats__milestone__idx
    ON SpecificationWorkItemStats(milestone) WHERE milestone IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 06, 1);
