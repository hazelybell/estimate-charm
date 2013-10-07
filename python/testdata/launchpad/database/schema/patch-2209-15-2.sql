SET client_min_messages=ERROR;

-- Missing foreign key constraint.
ALTER TABLE BugTag ADD CONSTRAINT bugtag__bug__fk FOREIGN KEY (bug) REFERENCES Bug;

-- We managed to get a second plpython handler installed in the public
-- namespace that is blocking pg_upgrade upgrades. PGBug #6532,
-- investigation on root cause ongoing.
DROP FUNCTION IF EXISTS public.plpython_call_handler();

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 15, 2);
