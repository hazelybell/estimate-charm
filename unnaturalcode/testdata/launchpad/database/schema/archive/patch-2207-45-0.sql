SET client_min_messages=ERROR;

/* Nuke some unused indexes */

DROP INDEX translationmessage__current_or_imported__idx;
DROP INDEX hwsubmissiondevice__parent__idx;
DROP INDEX shippingrequest__recipientdisplayname__idx;

/* This has gotten bloated */
reindex table oauthnonce;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 45, 0);
