-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Remove the old access policy schema.
ALTER TABLE AccessPolicy SET SCHEMA todrop;
ALTER TABLE AccessPolicyArtifact SET SCHEMA todrop;
ALTER TABLE AccessPolicyGrant SET SCHEMA todrop;

ALTER TABLE Bug DROP COLUMN access_policy;
ALTER TABLE Branch DROP COLUMN access_policy;

-- And create a whole new one.
CREATE TABLE AccessPolicy (
    id serial PRIMARY KEY,
    product integer REFERENCES product,
    distribution integer REFERENCES distribution,
    type integer NOT NULL,
    CONSTRAINT has_target CHECK (product IS NULL != distribution IS NULL)
);

CREATE UNIQUE INDEX accesspolicy__product__type__key
    ON AccessPolicy(product, type) WHERE product IS NOT NULL;
CREATE UNIQUE INDEX accesspolicy__distribution__type__key
    ON AccessPolicy(distribution, type) WHERE distribution IS NOT NULL;

CREATE TABLE AccessArtifact (
    id serial PRIMARY KEY,
    bug integer REFERENCES bug,
    branch integer, -- FK to be added later.
    CONSTRAINT has_artifact CHECK (bug IS NULL != branch IS NULL)
);

CREATE UNIQUE INDEX accessartifact__bug__key
    ON AccessArtifact(bug) WHERE bug IS NOT NULL;
CREATE UNIQUE INDEX accessartifact__branch__key
    ON AccessArtifact(branch) WHERE branch IS NOT NULL;

CREATE TABLE AccessPolicyArtifact (
    artifact integer REFERENCES AccessArtifact NOT NULL,
    policy integer REFERENCES AccessPolicy NOT NULL,
    PRIMARY KEY (artifact, policy)
);

CREATE INDEX accesspolicyartifact__policy__key
    ON AccessPolicyArtifact(policy);

CREATE TABLE AccessPolicyGrant (
    policy integer REFERENCES AccessPolicy NOT NULL,
    grantee integer NOT NULL, -- FK to be added later.
    grantor integer NOT NULL, -- FK to be added later.
    date_created timestamp without time zone
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    PRIMARY KEY (policy, grantee)
);

CREATE TABLE AccessArtifactGrant (
    artifact integer REFERENCES AccessArtifact NOT NULL,
    grantee integer NOT NULL, -- FK to be added later.
    grantor integer NOT NULL, -- FK to be added later.
    date_created timestamp without time zone
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') NOT NULL,
    PRIMARY KEY (artifact, grantee)
);

CREATE TABLE AccessPolicyGrantFlat (
    id serial PRIMARY KEY,
    policy integer REFERENCES AccessPolicy NOT NULL,
    artifact integer REFERENCES AccessArtifact,
    grantee integer NOT NULL -- FK to be added later.
);

CREATE UNIQUE INDEX accesspolicygrantflat__policy__grantee__key
    ON AccessPolicyGrantFlat(policy, grantee) WHERE artifact IS NULL;
CREATE UNIQUE INDEX accesspolicygrantflat__policy__grantee__artifact__key
    ON AccessPolicyGrantFlat(policy, grantee, artifact);
CREATE INDEX accesspolicygrantflat__artifact__grantee__idx
    ON AccessPolicyGrantFlat(artifact, grantee);


-- TRIGGERS
-----------

-- AccessPolicyArtifact

CREATE OR REPLACE FUNCTION
    accesspolicyartifact_maintain_accesspolicyartifactflat_trig()
    RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO AccessPolicyGrantFlat
            (policy, artifact, grantee)
            SELECT NEW.policy, NEW.artifact, grantee
                FROM AccessArtifactGrant WHERE artifact = NEW.artifact;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.policy != OLD.policy OR NEW.artifact != OLD.artifact THEN
            UPDATE AccessPolicyGrantFlat
                SET policy=NEW.policy, artifact=NEW.artifact
                WHERE policy = OLD.policy AND artifact = OLD.artifact;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM AccessPolicyGrantFlat
            WHERE policy = OLD.policy AND artifact = OLD.artifact;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER accesspolicyartifact_maintain_accesspolicyartifactflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accesspolicyartifact
    FOR EACH ROW EXECUTE PROCEDURE
        accesspolicyartifact_maintain_accesspolicyartifactflat_trig();


-- AccessArtifactGrant

CREATE OR REPLACE FUNCTION
    accessartifactgrant_maintain_accesspolicygrantflat_trig()
    RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO AccessPolicyGrantFlat
            (policy, artifact, grantee)
            SELECT policy, NEW.artifact, NEW.grantee
                FROM AccessPolicyArtifact WHERE artifact = NEW.artifact;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.artifact != OLD.artifact OR NEW.grantee != OLD.grantee THEN
            UPDATE AccessPolicyGrantFlat
                SET artifact=NEW.artifact, grantee=NEW.grantee
                WHERE artifact = OLD.artifact AND grantee = OLD.grantee;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM AccessPolicyGrantFlat
            WHERE artifact = OLD.artifact AND grantee = OLD.grantee;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER accessartifactgrant_maintain_accesspolicygrantflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accessartifactgrant
    FOR EACH ROW EXECUTE PROCEDURE
        accessartifactgrant_maintain_accesspolicygrantflat_trig();


-- AccessPolicyGrant

CREATE OR REPLACE FUNCTION
    accesspolicygrant_maintain_accesspolicygrantflat_trig()
    RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO AccessPolicyGrantFlat
            (policy, grantee) VALUES (NEW.policy, NEW.grantee);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.policy != OLD.policy OR NEW.grantee != OLD.grantee THEN
            UPDATE AccessPolicyGrantFlat
                SET policy=NEW.policy, grantee=NEW.grantee
                WHERE
                    policy = OLD.policy
                    AND grantee = OLD.grantee
                    AND artifact IS NULL;
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM AccessPolicyGrantFlat
            WHERE
                policy = OLD.policy
                AND grantee = OLD.grantee
                AND artifact IS NULL;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER accesspolicygrant_maintain_accesspolicygrantflat_trigger
    AFTER INSERT OR UPDATE OR DELETE ON accesspolicygrant
    FOR EACH ROW EXECUTE PROCEDURE
        accesspolicygrant_maintain_accesspolicygrantflat_trig();


INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 1);
