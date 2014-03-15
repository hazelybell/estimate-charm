-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;


CREATE OR REPLACE FUNCTION bug_summary_flush_temp_journal() RETURNS VOID
LANGUAGE plpgsql VOLATILE AS
$$
DECLARE
    d bugsummary%ROWTYPE;
BEGIN
    -- may get called even though no summaries were made (for simplicity in the
    -- callers)
    PERFORM ensure_bugsummary_temp_journal();
    FOR d IN SELECT * FROM bugsummary_temp_journal LOOP
        PERFORM bugsummary_journal_ins(d);
    END LOOP;
    TRUNCATE bugsummary_temp_journal;
END;
$$;

COMMENT ON FUNCTION bug_summary_flush_temp_journal() IS
'flush the temporary bugsummary journal into the bugsummaryjournal table';


INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 75, 1);
