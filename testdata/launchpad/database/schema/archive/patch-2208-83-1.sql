SET client_min_messages=ERROR;

-- Remove Person FKs.
ALTER TABLE authtoken DROP CONSTRAINT authtoken__requester__fk;
ALTER TABLE bounty DROP CONSTRAINT bounty_claimant_fk;
ALTER TABLE bounty DROP CONSTRAINT bounty_owner_fk;
ALTER TABLE bounty DROP CONSTRAINT bounty_reviewer_fk;
ALTER TABLE bountysubscription DROP CONSTRAINT bountysubscription_person_fk;
ALTER TABLE bugpackageinfestation DROP CONSTRAINT bugpackageinfestation_creator_fk;
ALTER TABLE bugpackageinfestation DROP CONSTRAINT bugpackageinfestation_lastmodifiedby_fk;
ALTER TABLE bugpackageinfestation DROP CONSTRAINT bugpackageinfestation_verifiedby_fk;
ALTER TABLE bugproductinfestation DROP CONSTRAINT bugproductinfestation_creator_fk;
ALTER TABLE bugproductinfestation DROP CONSTRAINT bugproductinfestation_lastmodifiedby_fk;
ALTER TABLE bugproductinfestation DROP CONSTRAINT bugproductinfestation_verifiedby_fk;
ALTER TABLE distrocomponentuploader DROP CONSTRAINT distrocomponentuploader_uploader_fk;
ALTER TABLE mailinglistban DROP CONSTRAINT mailinglistban_banned_by_fkey;
ALTER TABLE mailinglistban DROP CONSTRAINT mailinglistban_person_fkey;
ALTER TABLE mentoringoffer DROP CONSTRAINT mentoringoffer_owner_fkey;
ALTER TABLE mentoringoffer DROP CONSTRAINT mentoringoffer_team_fkey;
ALTER TABLE packagebugsupervisor DROP CONSTRAINT packagebugsupervisor__bug_supervisor__fk;
ALTER TABLE posubscription DROP CONSTRAINT "$1";
ALTER TABLE pushmirroraccess DROP CONSTRAINT "$1";
ALTER TABLE webserviceban DROP CONSTRAINT webserviceban_person_fkey;
ALTER TABLE openidrpsummary DROP CONSTRAINT openidrpsummary_account_fkey;
ALTER TABLE pocomment DROP CONSTRAINT "$5";

-- Remove LFA FKs.
ALTER TABLE shipitreport DROP CONSTRAINT "$1";
ALTER TABLE shippingrun DROP CONSTRAINT shippingrun_csvfile_fk;
ALTER TABLE openidrpconfig DROP CONSTRAINT openidrpconfig__logo__fk;

-- Unreference staticdiff.
ALTER TABLE branchmergeproposal DROP COLUMN review_diff;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 83, 1);
