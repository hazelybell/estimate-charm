-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION update_transitively_private(
    start_branch int,
    _root_branch int = NULL,
    _root_transitively_private boolean = NULL) RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path TO PUBLIC AS
$$
DECLARE
    root_transitively_private boolean := _root_transitively_private;
    root_branch int := _root_branch;
BEGIN
    IF root_transitively_private IS NULL THEN
        -- We can't just trust the transitively_private flag of the
        -- branch we are stacked on, as if we are updating multiple
        -- records they will be updated in an indeterminate order.
        -- We need a recursive query.
        UPDATE Branch SET transitively_private = (
            WITH RECURSIVE stacked_branches AS (
                SELECT
                    top_branch.id, top_branch.stacked_on, top_branch.private
                FROM Branch AS top_branch
                WHERE top_branch.id = start_branch
                UNION ALL
                SELECT
                    sub_branch.id, sub_branch.stacked_on, sub_branch.private
                FROM stacked_branches, Branch AS sub_branch
                WHERE
                    stacked_branches.stacked_on = sub_branch.id
                    AND stacked_branches.stacked_on != start_branch
                    -- Shortcircuit. No need to recurse if already private.
                    AND stacked_branches.private IS FALSE
                    )
            SELECT COUNT(*) > 0
            FROM stacked_branches
            WHERE private IS TRUE)
        WHERE Branch.id = start_branch
        RETURNING transitively_private INTO root_transitively_private;
        root_branch := start_branch;
    ELSE
        -- Now we have calculated the correct transitively_private flag
        -- we can trust it.
        UPDATE Branch SET
            transitively_private = GREATEST(private, root_transitively_private)
        WHERE id = root_branch;
    END IF;

    -- Recurse to branches stacked on this one.
    PERFORM update_transitively_private(
        start_branch, id, GREATEST(private, root_transitively_private))
    FROM Branch WHERE stacked_on = root_branch AND id != start_branch;
END;
$$;

COMMENT ON FUNCTION update_transitively_private(int, int, boolean) IS
'A branch is transitively private if it is private or is stacked on any transitively private branches.';

CREATE OR REPLACE FUNCTION maintain_transitively_private() RETURNS TRIGGER
LANGUAGE plpgsql VOLATILE AS
$$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (NEW.stacked_on IS NOT DISTINCT FROM OLD.stacked_on
            AND NEW.private IS NOT DISTINCT FROM OLD.private) THEN
            RETURN NULL;
        END IF;
    END IF;
    PERFORM update_transitively_private(NEW.id);
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION maintain_transitively_private() IS
    'Trigger maintaining the Branch transitively_private column';

CREATE TRIGGER maintain_branch_transitive_privacy_t
    AFTER INSERT OR UPDATE ON Branch
    FOR EACH ROW
    EXECUTE PROCEDURE maintain_transitively_private();

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 87, 1);
