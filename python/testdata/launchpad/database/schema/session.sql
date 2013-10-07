-- Create tables used by the Z3 PostgreSQL session storage.
--
-- The PostgreSQL user that the session machinery connects as needs to be
-- granted the following permissions to the user the Zope 3 session machinery
-- is configured to connect as:
--   GRANT SELECT, INSERT, UPDATE, DELETE ON SessionData TO z3session;
--   GRANT SELECT, INSERT, UPDATE, DELETE oN SessionPkgData TO z3session;
--   GRANT SELECT ON Secret TO z3session;

SET client_min_messages=ERROR;

CREATE TABLE Secret (secret text) WITHOUT OIDS;
COMMENT ON TABLE Secret IS 'The Zope3 session machinery uses a secret to cryptographically sign the tokens, stopping people creating arbitrary tokens and detecting corrupt or modified tokens. This secret is stored in this table where it can be accessed by all Z3 instances using the database';

INSERT INTO Secret VALUES ('thooper thpetial theqwet');

CREATE TABLE SessionData (
    client_id     text PRIMARY KEY,
    created       timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) WITHOUT OIDS;
COMMENT ON TABLE SessionData IS 'Stores session tokens (the client_id) and the last accessed timestamp. The precision of the last access time is dependant on configuration in the Z3 application servers.';

CREATE INDEX sessiondata_last_accessed_idx ON SessionData(last_accessed);

CREATE TABLE SessionPkgData (
    client_id  text NOT NULL
        REFERENCES SessionData(client_id) ON DELETE CASCADE,
    product_id text NOT NULL,
    key        text NOT NULL,
    pickle     bytea NOT NULL,
    CONSTRAINT sessionpkgdata_pkey PRIMARY KEY (client_id, product_id, key)
    ) WITHOUT OIDS;
COMMENT ON TABLE SessionPkgData IS 'Stores the actual session data as a Python pickle.';

CREATE OR REPLACE FUNCTION ensure_session_client_id(p_client_id text)
RETURNS VOID AS $$
BEGIN
    INSERT INTO SessionData (client_id) VALUES (p_client_id);
EXCEPTION WHEN unique_violation THEN
    -- Do nothing
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION set_session_pkg_data(
    p_client_id text, p_product_id text, p_key text, p_pickle bytea
    ) RETURNS VOID AS $$
BEGIN
    -- Standard upsert loop to avoid race conditions
    LOOP
        -- Attempt an UPDATE first
        UPDATE SessionPkgData SET pickle = p_pickle
        WHERE client_id = p_client_id
            AND product_id = p_product_id
            AND key = p_key;
        IF found THEN
            RETURN;
        END IF;

        -- Next try an insert
        BEGIN
            INSERT INTO SessionPkgData (client_id, product_id, key, pickle)
            VALUES (p_client_id, p_product_id, p_key, p_pickle);
            RETURN;

        -- If the INSERT fails, another connection did the INSERT before us
        -- so ignore and try update again next loop.
        EXCEPTION WHEN unique_violation THEN
            -- Do nothing
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

