-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages = ERROR;

-- Drop old unused functions still lurking on production.
DROP FUNCTION IF EXISTS is_blacklisted_name(text);
DROP FUNCTION IF EXISTS name_blacklist_match(text);
DROP FUNCTION IF EXISTS reverse(text);
DROP FUNCTION IF EXISTS bug_summary_temp_journal_clean_row(bugsummary);
DROP FUNCTION IF EXISTS valid_version(text);
DROP FUNCTION IF EXISTS decendantrevision(integer);
DROP FUNCTION IF EXISTS sleep_for_testing(float);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 76, 3);
