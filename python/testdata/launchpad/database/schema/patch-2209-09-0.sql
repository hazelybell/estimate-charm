-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE entitlement DROP CONSTRAINT entitlement_approved_by_fkey;
ALTER TABLE entitlement DROP CONSTRAINT entitlement_person_fkey;
ALTER TABLE entitlement DROP CONSTRAINT entitlement_registrant_fkey;

ALTER TABLE entitlement SET SCHEMA todrop;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 09, 0);

