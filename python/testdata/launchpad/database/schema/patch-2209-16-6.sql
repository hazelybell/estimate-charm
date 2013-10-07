-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Create new access policy for Branch.
ALTER TABLE Branch ADD COLUMN access_policy integer;
ALTER TABLE Branch ADD COLUMN access_grants integer[];

-- New function, shared between artifact types.
CREATE OR REPLACE FUNCTION build_access_cache(art_id integer,
                                              information_type integer)
    RETURNS record
    LANGUAGE plpgsql
    AS $$
DECLARE
    _policies integer[];
    _grants integer[];
    cache record;
BEGIN
    -- If private, grab the access control information.
    -- If public, access_policies and access_grants are NULL.
    -- 3 == PRIVATESECURITY, 4 == USERDATA, 5 == PROPRIETARY
    IF information_type IN (3, 4, 5) THEN
        SELECT COALESCE(array_agg(policy ORDER BY policy), ARRAY[]::integer[])
            INTO _policies FROM accesspolicyartifact WHERE artifact = art_id;
        SELECT COALESCE(array_agg(grantee ORDER BY grantee), ARRAY[]::integer[])
            INTO _grants FROM accessartifactgrant WHERE artifact = art_id;
    END IF;
    cache := (_policies, _grants);
    RETURN cache;
END;
$$;


-- Reimplement old bug functions in terms of new shared one.
CREATE OR REPLACE FUNCTION bug_build_access_cache(bug_id integer,
                                                  information_type integer)
    RETURNS record LANGUAGE sql AS $$
    SELECT build_access_cache(
        (SELECT id FROM accessartifact WHERE bug = $1), $2);
$$;

CREATE OR REPLACE FUNCTION bug_flatten_access(bug_id integer)
    RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE bugtaskflat
        SET access_policies = policies, access_grants = grants
        FROM
            build_access_cache(
                (SELECT id FROM accessartifact WHERE bug = $1),
                (SELECT information_type FROM bug WHERE id = $1))
            AS (policies integer[], grants integer[])
        WHERE bug = $1;
$$;


-- New branch function, like bug_flatten_access.
CREATE OR REPLACE FUNCTION branch_denorm_access(branch_id integer)
    RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE branch
        SET access_policy = policies[1], access_grants = grants
        FROM
            build_access_cache(
                (SELECT id FROM accessartifact WHERE branch = $1),
                (SELECT information_type FROM branch WHERE id = $1))
            AS (policies integer[], grants integer[])
        WHERE id = $1;
$$;


-- Replace the machinery that maintains the denormalized columns in BugTaskFlat
-- with functions/triggers that deals with both bugs and branches.
DROP TRIGGER accesspolicyartifact_maintain_bugtaskflat_trigger ON AccessPolicyArtifact;
DROP TRIGGER accessartifactgrant_maintain_bugtaskflat_trigger ON AccessArtifactGrant;
DROP FUNCTION accessartifact_flatten_bug(integer);
DROP FUNCTION accessartifact_maintain_bugtaskflat_trig();

CREATE OR REPLACE FUNCTION accessartifact_denorm_to_artifacts(artifact_id integer)
    RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    artifact_row accessartifact%ROWTYPE;
BEGIN
    SELECT * INTO artifact_row FROM accessartifact WHERE id = artifact_id;
    IF artifact_row.bug IS NOT NULL THEN
        PERFORM bug_flatten_access(artifact_row.bug);
    END IF;
    IF artifact_row.branch IS NOT NULL THEN
        PERFORM branch_denorm_access(artifact_row.branch);
    END IF;
    RETURN;
END;
$$;
COMMENT ON FUNCTION accessartifact_denorm_to_artifacts(artifact_id integer) IS
    'Denormalize the policy access and artifact grants to bugs and branches.';

CREATE OR REPLACE FUNCTION accessartifact_maintain_denorm_to_artifacts_trig()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM accessartifact_denorm_to_artifacts(NEW.artifact);
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM accessartifact_denorm_to_artifacts(NEW.artifact);
        IF OLD.artifact != NEW.artifact THEN
            PERFORM accessartifact_denorm_to_artifacts(OLD.artifact);
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM accessartifact_denorm_to_artifacts(OLD.artifact);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER accesspolicyartifact_denorm_to_artifacts_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accesspolicyartifact
    FOR EACH ROW EXECUTE PROCEDURE accessartifact_maintain_denorm_to_artifacts_trig();

CREATE TRIGGER accessartifactgrant_denorm_to_artifacts_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accessartifactgrant
    FOR EACH ROW EXECUTE PROCEDURE accessartifact_maintain_denorm_to_artifacts_trig();


-- A trigger to handle Branch.information_type changes.
CREATE OR REPLACE FUNCTION branch_maintain_access_cache_trig() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    PERFORM branch_denorm_access(NEW.id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER branch_maintain_access_cache
    AFTER INSERT OR UPDATE OF information_type ON branch
    FOR EACH ROW EXECUTE PROCEDURE branch_maintain_access_cache_trig();


-- And delete the old privacy columns and trigger.
ALTER TABLE Branch DROP COLUMN private;
ALTER TABLE Branch DROP COLUMN transitively_private;
DROP TRIGGER maintain_branch_transitive_privacy_t ON Branch;
DROP FUNCTION maintain_transitively_private();

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 16, 6);
