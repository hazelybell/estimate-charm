-- Copyright 2009 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

-- Create the standard session tables.

\i session.sql

-- Grant required permissions on these tables to the 'session' user.
GRANT SELECT, INSERT, UPDATE, DELETE ON SessionData TO session;
GRANT SELECT, INSERT, UPDATE, DELETE oN SessionPkgData TO session;
GRANT SELECT ON Secret TO session;

GRANT EXECUTE ON FUNCTION ensure_session_client_id(text) TO session;
GRANT EXECUTE ON FUNCTION
    set_session_pkg_data(text, text, text, bytea) TO session;

CREATE TABLE TimeLimitedToken (
    path text NOT NULL,
    token text NOT NULL,
    created timestamp without time zone
        NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    constraint timelimitedtoken_pkey primary key (path, token)
    ) WITHOUT OIDS;
COMMENT ON TABLE TimeLimitedToken IS 'stores tokens for granting access to a single path in the librarian for a short while. The garbo takes care of cleanups, and we should only have a few thousand at a time. Tokens are handed out just-in-time on the appserver, when a client attempts to dereference a private thing which we do not want to deliver in-line. OAuth tokens cannot be used for the launchpadlibrarian content because they would then be attackable. See lib.lp.services.database.librarian for the python class.';
-- Give the garbo an efficient selection to cleanup
CREATE INDEX timelimitedtoken_created ON TimeLimitedToken(created);

-- Let the session user access file access tokens.
GRANT SELECT, INSERT, UPDATE, DELETE ON TimeLimitedToken TO session;
-- And the garbo needs to run on it too.
GRANT SELECT, DELETE ON TimeLimitedToken TO session;


-- This helper needs to exist in the session database so the BulkPruner
-- can clean up unwanted sessions.
CREATE OR REPLACE FUNCTION cursor_fetch(cur refcursor, n integer)
RETURNS SETOF record LANGUAGE plpgsql AS
$$
DECLARE
    r record;
    count integer;
BEGIN
    FOR count IN 1..n LOOP
        FETCH FORWARD FROM cur INTO r;
        IF NOT FOUND THEN
            RETURN;
        END IF;
        RETURN NEXT r;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION cursor_fetch(refcursor, integer) IS
'Fetch the next n items from a cursor. Work around for not being able to use FETCH inside a SELECT statement.';

GRANT EXECUTE ON FUNCTION cursor_fetch(refcursor, integer) TO session;
