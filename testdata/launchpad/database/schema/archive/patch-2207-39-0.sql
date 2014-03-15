SET client_min_messages=ERROR;

CREATE TABLE BugWatchActivity(
    id serial NOT NULL PRIMARY KEY,
    bug_watch integer NOT NULL REFERENCES BugWatch(id),
    activity_date timestamp without time zone
        DEFAULT timezone('UTC'::text, now()) NOT NULL,
    result integer,
    message text,
    oops_id text
);

CREATE INDEX bugwatchactivity__date__idx ON BugWatchActivity(activity_date);
CREATE INDEX bugwatchactivity__bug_watch__idx ON BugWatchActivity(bug_watch);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 39, 0);
