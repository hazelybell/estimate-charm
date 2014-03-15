-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Magical superfunction to bring a bug's new access data into consistency
-- with its legacy data.

CREATE OR REPLACE FUNCTION bug_mirror_legacy_access(bug_id integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    bug_row record;
    artifact_id integer;
    bugtask_row record;
    policy_type integer;
    pillars record;
    access_policies integer[];
BEGIN
    SELECT * INTO bug_row FROM bug WHERE id = bug_id;
    SELECT id INTO artifact_id FROM AccessArtifact WHERE bug = bug_id;
    IF NOT bug_row.private THEN
        IF artifact_id IS NOT NULL THEN
            -- Bug is public, but there are access control rows. Destroy them.
            DELETE FROM AccessArtifactGrant WHERE artifact = artifact_id;
            DELETE FROM AccessPolicyArtifact WHERE artifact = artifact_id;
            DELETE FROM AccessArtifact WHERE id = artifact_id;
        END IF;
    ELSE
        -- Bug is private. Add missing rows, remove superfluous ones.

        -- Ensure that there's a corresponding AccessArtifact.
        IF artifact_id IS NULL THEN
            INSERT INTO AccessArtifact (bug) VALUES (bug_row.id)
                RETURNING id INTO artifact_id;
        END IF;

        -- Ensure that the AccessArtifactGrants match BugSubscriptions.
        DELETE FROM AccessArtifactGrant
            WHERE
                artifact = artifact_id
                AND grantee NOT IN (
                    SELECT person FROM bugsubscription WHERE bug = bug_id);
        INSERT INTO AccessArtifactGrant
            (artifact, grantee, grantor, date_created)
            SELECT DISTINCT ON (artifact_id, BugSubscription.person)
                   artifact_id, BugSubscription.person,
                   BugSubscription.subscribed_by, BugSubscription.date_created
                FROM
                    BugSubscription
                    LEFT JOIN AccessArtifactGrant
                        ON (AccessArtifactGrant.grantee =
                                BugSubscription.person
                            AND AccessArtifactGrant.artifact = artifact_id)
                WHERE
                    AccessArtifactGrant.grantee IS NULL
                    AND BugSubscription.bug = bug_id
                ORDER BY
                    artifact_id,
                    BugSubscription.person,
                    BugSubscription.date_created;

        -- Ensure that AccessPolicyArtifacts match the implied policy
        -- type and the tasks' pillars.
        SELECT (CASE
                    WHEN NOT bug_row.security_related THEN 4
                    WHEN bug_row.security_related THEN 3
                END) INTO policy_type;
        SELECT
            array_agg(
                DISTINCT COALESCE(bugtask.product, productseries.product))
                AS products,
            array_agg(
                DISTINCT COALESCE(bugtask.distribution,
                                  distroseries.distribution))
                AS distributions
            INTO pillars
            FROM
                bugtask
                LEFT JOIN productseries
                    ON productseries.id = bugtask.productseries
                LEFT JOIN distroseries
                    ON distroseries.id = bugtask.distroseries
            WHERE bug = bug_id;
        SELECT array_agg(id) FROM AccessPolicy
            INTO access_policies
            WHERE 
                type = policy_type
                AND (
                    (product IS NOT NULL AND product = ANY(pillars.products))
                    OR (distribution IS NOT NULL
                        AND distribution = ANY(pillars.distributions)));
        DELETE FROM AccessPolicyArtifact
            WHERE
                artifact = artifact_id
            AND policy != ALL(access_policies);
        INSERT INTO AccessPolicyArtifact
            (artifact, policy)
            SELECT DISTINCT artifact_id, policy
                FROM unnest(access_policies) AS policy
            EXCEPT
            SELECT artifact_id, policy FROM AccessPolicyArtifact
                WHERE artifact = artifact_id;
    END IF;
END;
$$;

-- Bug triggers

CREATE OR REPLACE FUNCTION bug_mirror_legacy_access_trig() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bug_mirror_legacy_access(NEW.id);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.private != OLD.private OR NEW.security_related != OLD.security_related THEN
            PERFORM bug_mirror_legacy_access(OLD.id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;


DROP TRIGGER IF EXISTS bug_mirror_legacy_access_t ON bug;
CREATE TRIGGER bug_mirror_legacy_access_t
    AFTER INSERT OR UPDATE ON bug
    FOR EACH ROW EXECUTE PROCEDURE bug_mirror_legacy_access_trig();


-- BugTask triggers

CREATE OR REPLACE FUNCTION bugtask_mirror_legacy_access_trig() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bug_mirror_legacy_access(NEW.bug);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.bug != OLD.bug THEN
            RAISE EXCEPTION 'cannot move bugtask to a different bug';
        END IF;
        IF (NEW.distribution IS DISTINCT FROM OLD.distribution
            OR NEW.product IS DISTINCT FROM OLD.product
            OR NEW.distroseries IS DISTINCT FROM OLD.distroseries
            OR NEW.productseries IS DISTINCT FROM OLD.productseries) THEN
            PERFORM bug_mirror_legacy_access(OLD.bug);
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM bug_mirror_legacy_access(OLD.bug);
    END IF;
    RETURN NULL;
END;
$$;


DROP TRIGGER IF EXISTS bugtask_mirror_legacy_access_t ON bugtask;
CREATE TRIGGER bugtask_mirror_legacy_access_t
    AFTER INSERT OR UPDATE OR DELETE ON bugtask
    FOR EACH ROW EXECUTE PROCEDURE bugtask_mirror_legacy_access_trig();


-- BugSubscription triggers

CREATE OR REPLACE FUNCTION bugsubscription_mirror_legacy_access_trig() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bug_mirror_legacy_access(NEW.bug);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.bug != OLD.bug THEN
            RAISE EXCEPTION 'cannot move bugsubscription to a different bug';
        END IF;
        IF NEW.person != OLD.person THEN
            PERFORM bug_mirror_legacy_access(OLD.bug);
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM bug_mirror_legacy_access(OLD.bug);
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS
    bugsubscription_mirror_legacy_access_t ON bugsubscription;
CREATE TRIGGER bugsubscription_mirror_legacy_access_t
    AFTER INSERT OR UPDATE OR DELETE ON bugsubscription
    FOR EACH ROW EXECUTE PROCEDURE bugsubscription_mirror_legacy_access_trig();

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 3);
