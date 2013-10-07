-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE SpecificationFeedback DROP CONSTRAINT specificationfeedback_specification_fk;
ALTER TABLE SpecificationFeedback SET SCHEMA todrop;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 20, 1);
