SET client_min_messages = ERROR;

create index bug__new_patches__idx on bug(id)
where latest_patch_uploaded IS NOT NULL AND duplicateof IS NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 65, 1);

