SET client_min_messages=ERROR;

CREATE EXTENSION plpythonu FROM unpackaged;
-- Do this after upgrades to Ubuntu 12.04 to avoid backporting
--CREATE EXTENSION debversion FROM unpackaged;

-- Per PGBug 7661, clean our our old unpackaged pgstattuple. It is too
-- ancient for the 9.1.6 upgrade script to work with.
DROP FUNCTION pgstattuple(text);
DROP FUNCTION pgstattuple(oid);
DROP FUNCTION IF EXISTS pgstatindex(text);
DROP FUNCTION IF EXISTS pg_relpages(text);

CREATE EXTENSION pgstattuple;

-- Similarly, our tsearch2 compatibility dates from 8.3 and fails to upgrade.
-- No bug reported here, as we may have messed with our tsearch2 stuff.
-- Manually create the missing bits, sourcing code from
-- extensions/tsearch2--1.0.sql
CREATE OPERATOR CLASS ts2.gist_tsvector_ops
FOR TYPE tsvector USING gist
AS
        OPERATOR        1       @@ (tsvector, tsquery),
        FUNCTION        1       gtsvector_consistent (internal,
                                    gtsvector, int, oid, internal),
        FUNCTION        2       gtsvector_union (internal, internal),
        FUNCTION        3       gtsvector_compress (internal),
        FUNCTION        4       gtsvector_decompress (internal),
        FUNCTION        5       gtsvector_penalty (
                                    internal, internal, internal),
        FUNCTION        6       gtsvector_picksplit (internal, internal),
        FUNCTION        7       gtsvector_same (
                                    gtsvector, gtsvector, internal),
        STORAGE         gtsvector;

CREATE OPERATOR CLASS ts2.gist_tp_tsquery_ops
FOR TYPE tsquery USING gist
AS
        OPERATOR        7       @> (tsquery, tsquery),
        OPERATOR        8       <@ (tsquery, tsquery),
        FUNCTION        1       gtsquery_consistent (
                                    internal, internal, int, oid, internal),
        FUNCTION        2       gtsquery_union (internal, internal),
        FUNCTION        3       gtsquery_compress (internal),
        FUNCTION        4       gtsquery_decompress (internal),
        FUNCTION        5       gtsquery_penalty (
                                    internal, internal, internal),
        FUNCTION        6       gtsquery_picksplit (internal, internal),
        FUNCTION        7       gtsquery_same (bigint, bigint, internal),
        STORAGE         bigint;

CREATE OPERATOR CLASS ts2.gin_tsvector_ops
FOR TYPE tsvector USING gin
AS
        OPERATOR        1       @@ (tsvector, tsquery),
        OPERATOR        2       @@@ (tsvector, tsquery),
        FUNCTION        1       bttextcmp(text, text),
        FUNCTION        2       gin_extract_tsvector(
                                    tsvector,internal,internal),
        FUNCTION        3       gin_extract_tsquery(
                                    tsquery,internal,smallint,
                                    internal,internal,internal,internal),
        FUNCTION        4       gin_tsquery_consistent(
                                    internal,smallint,tsquery,int,
                                    internal,internal,internal,internal),
        FUNCTION        5       gin_cmp_prefix(text,text,smallint,internal),
        STORAGE         text;


CREATE EXTENSION tsearch2 SCHEMA ts2 FROM unpackaged;



INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 39, 0);
