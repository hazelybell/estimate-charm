SET client_min_messages=ERROR;

ALTER TABLE CodeImport ADD COLUMN url text;
UPDATE CodeImport SET url = git_repo_url WHERE rcs_type = 4;
UPDATE CodeImport SET url = svn_branch_url WHERE rcs_type IN (2, 3);
DROP INDEX codeimport__svn_branch_url__idx;
DROP INDEX codeimport__git_repo_url__idx;
ALTER TABLE CodeImport DROP CONSTRAINT valid_vcs_details;
ALTER TABLE CodeImport ADD CONSTRAINT "valid_vcs_details" CHECK (
CASE
    WHEN rcs_type = 1
         THEN cvs_root IS NOT NULL AND cvs_root <> ''::text AND cvs_module IS NOT NULL AND cvs_module <> ''::text
              AND url IS NULL
    WHEN rcs_type IN (2, 3)
         THEN cvs_root IS NULL AND cvs_module IS NULL
              AND url IS NOT NULL AND valid_absolute_url(url)
    WHEN rcs_type IN (4, 5)
         -- Git and mercurial imports are not checked for valid urls right now,
         -- this is a bug - 506146
         THEN cvs_root IS NULL AND cvs_module IS NULL AND url IS NOT NULL
    ELSE false
END);
ALTER TABLE CodeImport DROP COLUMN git_repo_url;
ALTER TABLE CodeImport DROP COLUMN svn_branch_url;

CREATE UNIQUE INDEX codeimport__url__idx ON CodeImport USING btree (url) WHERE (url is NOT NULL);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 26, 0);
