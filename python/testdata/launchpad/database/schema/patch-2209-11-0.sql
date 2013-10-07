-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Prepare to remove the old access policy schema.
ALTER TABLE Branch DROP CONSTRAINT branch_access_policy_fkey; 
ALTER TABLE Bug DROP CONSTRAINT bug_access_policy_fkey; 
ALTER TABLE AccessPolicyGrant DROP CONSTRAINT accesspolicygrant_grantee_fkey;
ALTER TABLE AccessPolicyGrant DROP CONSTRAINT accesspolicygrant_grantor_fkey;
ALTER TABLE AccessPolicyArtifact DROP CONSTRAINT accesspolicyartifact_branch_fkey;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 0);
