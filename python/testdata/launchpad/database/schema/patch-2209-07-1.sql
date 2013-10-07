-- Copyright 2012 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).
SET client_min_messages=ERROR;

CREATE OR REPLACE FUNCTION calculate_bug_heat(bug_id integer) RETURNS integer
 LANGUAGE sql STABLE STRICT AS $$
    SELECT
        (CASE private WHEN true THEN 150 ELSE 0 END)
        + (CASE security_related WHEN true THEN 250 ELSE 0 END)
        + (number_of_duplicates * 6)
        + (users_affected_count * 4)
        + (
            SELECT COUNT(DISTINCT person) * 2 
            FROM BugSubscription
            JOIN Bug AS SubBug ON BugSubscription.bug = SubBug.id
            WHERE SubBug.id = $1 OR SubBug.duplicateof = $1)::integer AS heat
    FROM Bug WHERE Bug.id = $1;
$$;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 07, 1);
