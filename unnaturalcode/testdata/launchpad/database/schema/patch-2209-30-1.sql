-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE accesspolicy ADD COLUMN person integer;

ALTER TABLE accesspolicy ALTER COLUMN type DROP NOT NULL;

ALTER TABLE accesspolicy DROP CONSTRAINT has_target; 

-- If person is set, then all other columns must be null.
-- If type is set, then either product or distribution must be set and person must be null.
ALTER TABLE accesspolicy ADD CONSTRAINT has_target
    CHECK (
      (type IS NOT NULL AND (product IS NULL <> distribution IS NULL) AND person IS NULL)
      OR
      (type IS NULL AND person IS NOT NULL and product IS NULL AND distribution IS NULL) );

ALTER TABLE ONLY accesspolicy
    ADD CONSTRAINT accesspolicy_person_fkey FOREIGN KEY (person) REFERENCES person(id);

COMMENT ON TABLE AccessPolicy IS 'An access policy used to manage a project, distribution or private team''s artifacts.';
COMMENT ON COLUMN AccessPolicy.person IS 'The private team that this policy is used on.';

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 30, 1);
