-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Bug 534203: this index makes POFile:+filter query use it even
-- when there's a better index on (potmsgset, language) to use.
-- It doesn't make sense anywhere else, but if we do turn out to
-- need it somewhere, we should include potmsgset in it as well.
-- (And perhaps drop translationmessage__potmsgset__language__idx).
DROP INDEX tm__language__submitter__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 76, 1);
