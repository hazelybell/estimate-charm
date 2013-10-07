-- Copyright 2013 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Create new access policy for Specification.
ALTER TABLE Specification ADD COLUMN access_policy integer;
ALTER TABLE Specification ADD COLUMN access_grants integer[];

-- New specification function, like bug_flatten_access.
CREATE OR REPLACE FUNCTION specification_denorm_access(spec_id integer)
    RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    UPDATE specification
        SET access_policy = policies[1], access_grants = grants
        FROM
            build_access_cache(
                (SELECT id FROM accessartifact WHERE specification = $1),
                (SELECT information_type FROM specification WHERE id = $1))
            AS (policies integer[], grants integer[])
        WHERE id = $1;
$$;

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
    IF artifact_row.specification IS NOT NULL THEN
        PERFORM specification_denorm_access(artifact_row.specification);
    END IF;
    RETURN;
END;
$$;
COMMENT ON FUNCTION accessartifact_denorm_to_artifacts(artifact_id integer) IS
    'Denormalize the policy access and artifact grants to bugs, branches and specifications.';

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

-- A trigger to handle specification.information_type changes.
CREATE OR REPLACE FUNCTION specification_maintain_access_cache_trig() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    PERFORM specification_denorm_access(NEW.id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER specification_maintain_access_cache
    AFTER INSERT OR UPDATE OF information_type ON specification
    FOR EACH ROW EXECUTE PROCEDURE specification_maintain_access_cache_trig();

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 28, 6);
