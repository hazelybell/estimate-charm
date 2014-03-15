-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

ALTER TABLE AccessArtifactGrant ADD CONSTRAINT
    accessartifactgrant__grantee__fk FOREIGN KEY (grantee) REFERENCES Person;
ALTER TABLE AccessArtifactGrant ADD CONSTRAINT
    accessartifactgrant__grantor__fk FOREIGN KEY (grantor) REFERENCES Person;
ALTER TABLE AccessPolicyGrant ADD CONSTRAINT
    accesspolicygrant__grantee__fk FOREIGN KEY (grantee) REFERENCES Person;
ALTER TABLE AccessPolicyGrant ADD CONSTRAINT
    accesspolicygrant__grantor__fk FOREIGN KEY (grantor) REFERENCES Person;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 5);
