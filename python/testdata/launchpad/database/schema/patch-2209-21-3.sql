SET client_min_messages = ERROR;

DROP INDEX archive_fti;
DROP INDEX message_fti;
DROP INDEX faq_fti;
DROP INDEX question_fti;
DROP INDEX binarypackagerelease_fti;
DROP INDEX distroseriespackagecache_fti;
DROP INDEX specification_fti;
DROP INDEX messagechunk_fti;
DROP INDEX project_fti;
DROP INDEX cve_fti;
DROP INDEX person_fti;
DROP INDEX bug_fti;
DROP INDEX distributionsourcepackagecache_fti;
DROP INDEX productreleasefile_fti;
DROP INDEX product_fti;
DROP INDEX distribution_fti;

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 21, 3);
