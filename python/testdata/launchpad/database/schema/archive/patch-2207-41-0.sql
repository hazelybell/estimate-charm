-- Copyright 2010 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;


alter table archivepermission drop constraint archivepermission__archive__fk;
ALTER TABLE ONLY archivepermission ADD CONSTRAINT archivepermission__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table build drop constraint build__archive__fk;
ALTER TABLE ONLY build ADD CONSTRAINT build__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table distributionsourcepackagecache drop constraint distributionsourcepackagecache__archive__fk;
ALTER TABLE ONLY distributionsourcepackagecache
    ADD CONSTRAINT distributionsourcepackagecache__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table distroseriespackagecache drop constraint distroseriespackagecache__archive__fk;
alter table distroseriespackagecache 
    add constraint distroseriespackagecache__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table packageupload drop constraint packageupload__archive__fk;
ALTER TABLE ONLY packageupload
    ADD CONSTRAINT packageupload__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table binarypackagepublishinghistory drop constraint securebinarypackagepublishinghistory__archive__fk;
ALTER TABLE ONLY binarypackagepublishinghistory
    ADD CONSTRAINT securebinarypackagepublishinghistory__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table sourcepackagepublishinghistory drop constraint securesourcepackagepublishinghistory__archive__fk;
alter table sourcepackagepublishinghistory ADD CONSTRAINT sourcepackagepublishinghistory__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table binarypackagerelease drop constraint binarypackagerelease_build_fk;
ALTER TABLE ONLY binarypackagerelease
    ADD CONSTRAINT binarypackagerelease__build__fk FOREIGN KEY (build) REFERENCES build(id) on delete cascade;

alter table packageuploadsource drop constraint packageuploadsource__packageupload__fk;
ALTER TABLE ONLY packageuploadsource
    ADD CONSTRAINT packageuploadsource__packageupload__fk FOREIGN KEY (packageupload) REFERENCES packageupload(id) on delete cascade;

alter table packageuploadbuild drop constraint packageuploadbuild_packageupload_fk;
ALTER TABLE ONLY packageuploadbuild
    ADD CONSTRAINT packageuploadbuild__packageupload__fk FOREIGN KEY (packageupload) REFERENCES packageupload(id) on delete cascade;

alter table sourcepackagereleasefile drop constraint "$1";
ALTER TABLE ONLY sourcepackagereleasefile
    ADD CONSTRAINT "$1" FOREIGN KEY (sourcepackagerelease) REFERENCES sourcepackagerelease(id) on delete cascade;

alter table binarypackagefile drop constraint binarypackagefile_binarypackagerelease_fk;
ALTER TABLE ONLY binarypackagefile
    ADD CONSTRAINT binarypackagefile_binarypackagerelease_fk FOREIGN KEY (binarypackagerelease) REFERENCES binarypackagerelease(id) on delete cascade;

alter table binarypackagereleasedownloadcount drop constraint binarypackagereleasedownloadcount_archive_fkey;
alter table binarypackagereleasedownloadcount 
    add constraint binarypackagereleasedownloadcount_archive_fkey FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table sourcepackagerecipebuild drop constraint sourcepackagerecipebuild_archive_fkey;
alter table sourcepackagerecipebuild 
    add constraint sourcepackagerecipebuild__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table archivearch drop constraint archivearch__archive__fk;
alter table archivearch 
    add constraint archivearch__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table archiveauthtoken drop constraint archiveauthtoken_archive_fkey;
alter table archiveauthtoken 
    add constraint archiveauthtoken__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table archivedependency drop constraint archivedependency_archive_fkey;
alter table archivedependency 
    add constraint archivedependency__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table archivedependency drop constraint archivedependency_dependency_fkey;
alter table archivedependency add 
    constraint archivedependency__dependency__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table archivesubscriber drop constraint archivesubscriber_archive_fkey;
alter table archivesubscriber 
    add constraint archivesubscriber__archive__fk FOREIGN KEY (archive) REFERENCES archive(id) on delete cascade;

alter table packagecopyrequest drop constraint packagecopyrequest__sourcearchive__fk;
alter table packagecopyrequest 
    add constraint packagecopyrequest__sourcearchive__fk FOREIGN KEY (source_archive) REFERENCES archive(id) on delete cascade;

alter table packagecopyrequest drop constraint packagecopyrequest__targetarchive__fk;
alter table packagecopyrequest 
    add constraint packagecopyrequest__targetarchive__fk FOREIGN KEY (target_archive) REFERENCES archive(id) on delete cascade;


-- If the upload_archive is deleted but the SPR was copied to a different
-- archive, then we allow this to be null to signify the original archive
-- was removed.
alter table sourcepackagerelease alter upload_archive drop not null;


INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 41, 0);
