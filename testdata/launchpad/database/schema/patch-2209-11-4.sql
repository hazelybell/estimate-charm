-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- These two functions are just like 2209-11-3 except using
-- information_type instead of private and security_related.

CREATE OR REPLACE FUNCTION bug_mirror_legacy_access(bug_id integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
    AS $$
DECLARE
    bug_row record;
    artifact_id integer;
    bugtask_row record;
    pillars record;
    access_policies integer[];
BEGIN
    SELECT * INTO bug_row FROM bug WHERE id = bug_id;
    SELECT id INTO artifact_id FROM AccessArtifact WHERE bug = bug_id;
    -- 3 == PRIVATESECURITY, 4 == USERDATA, 5 == PROPRIETARY
    IF bug_row.information_type NOT IN (3, 4, 5) THEN
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
                type = bug_row.information_type
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

CREATE OR REPLACE FUNCTION bug_mirror_legacy_access_trig() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM bug_mirror_legacy_access(NEW.id);
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.information_type IS DISTINCT FROM OLD.information_type THEN
            PERFORM bug_mirror_legacy_access(OLD.id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 11, 4);
