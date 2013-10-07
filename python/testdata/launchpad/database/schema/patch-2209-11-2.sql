-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Drop foreign keys within the old access policy model so slony can
-- drop them out of order.
ALTER TABLE todrop.AccessPolicyArtifact
    DROP CONSTRAINT accesspolicyartifact_policy_fkey; 
ALTER TABLE todrop.AccessPolicyGrant
    DROP CONSTRAINT accesspolicygrant_artifact_fkey; 
ALTER TABLE todrop.AccessPolicyGrant
    DROP CONSTRAINT accesspolicygrant_policy_fkey; 

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 2);
