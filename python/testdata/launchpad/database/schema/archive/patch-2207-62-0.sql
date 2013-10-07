SET client_min_messages=ERROR;

-- Bug #49717
ALTER TABLE SourcePackageRelease ALTER component SET NOT NULL;

-- We are taking OAuthNonce out of replication, so we make the foreign
-- key reference ON DELETE CASCADE so things don't explode when we
-- shuffle the lpmain master around.
ALTER TABLE OAuthNonce DROP CONSTRAINT oauthnonce__access_token__fk;
ALTER TABLE OAuthNonce ADD CONSTRAINT oauthnonce__access_token__fk
    FOREIGN KEY (access_token) REFERENCES OAuthAccessToken
    ON DELETE CASCADE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 62, 0);
