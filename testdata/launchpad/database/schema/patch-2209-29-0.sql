-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION public.bugsummary_viewers(btf_row bugtaskflat)
 RETURNS TABLE(viewed_by integer, access_policy integer)
 LANGUAGE sql
 IMMUTABLE
AS $function$
    SELECT NULL::integer, NULL::integer WHERE $1.information_type IN (1, 2)
    UNION ALL
    SELECT unnest($1.access_grants), NULL::integer
    WHERE $1.information_type NOT IN (1, 2)
    UNION ALL
    SELECT NULL::integer, unnest($1.access_policies)
    WHERE $1.information_type NOT IN (1, 2);
$function$;

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
    -- 6 == EMBARGOED
    IF information_type NOT IN (1, 2) THEN
        SELECT COALESCE(array_agg(policy ORDER BY policy), ARRAY[]::integer[])
            INTO _policies FROM accesspolicyartifact WHERE artifact = art_id;
        SELECT COALESCE(array_agg(grantee ORDER BY grantee), ARRAY[]::integer[])
            INTO _grants FROM accessartifactgrant WHERE artifact = art_id;
    END IF;
    cache := (_policies, _grants);
    RETURN cache;
END;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 29, 0);
