-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

ALTER TABLE AccessPolicyGrant ADD CONSTRAINT
    "accesspolicygrant_grantee_fkey" FOREIGN KEY (grantee) REFERENCES Person;
ALTER TABLE AccessPolicyGrant ADD CONSTRAINT
    "accesspolicygrant_grantor_fkey" FOREIGN KEY (grantor) REFERENCES Person;

ALTER TABLE AccessPolicyArtifact ADD CONSTRAINT
    "accesspolicyartifact_branch_fkey" FOREIGN KEY (branch) REFERENCES Branch;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 93, 2);
