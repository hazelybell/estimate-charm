SET client_min_messages=ERROR;

-- Remove interdependencies. upgrade.py drops replicated tables in
-- undefined order.
ALTER TABLE bountymessage DROP CONSTRAINT bountymessage_bounty_fk;
ALTER TABLE bountymessage DROP CONSTRAINT bountymessage_message_fk;
ALTER TABLE bountysubscription DROP CONSTRAINT bountysubscription_bounty_fk;
ALTER TABLE distributionbounty DROP CONSTRAINT distributionbounty_bounty_fk;
ALTER TABLE productbounty DROP CONSTRAINT productbounty_bounty_fk;
ALTER TABLE projectbounty DROP CONSTRAINT projectbounty_bounty_fk;
ALTER TABLE requestedcds DROP CONSTRAINT requestedcds_request_fk;
ALTER TABLE shipitsurveyresult DROP CONSTRAINT shipitsurveyresult_answer_fkey;
ALTER TABLE shipitsurveyresult DROP CONSTRAINT shipitsurveyresult_question_fkey;
ALTER TABLE shipitsurveyresult DROP CONSTRAINT shipitsurveyresult_survey_fkey;
ALTER TABLE shipment DROP CONSTRAINT shipment_shippingrun_fk;
ALTER TABLE shippingrequest DROP CONSTRAINT shippingrequest_shipment_fk;

-- And now actually dispose of all the tables.
ALTER TABLE authtoken SET SCHEMA todrop;
ALTER TABLE bounty SET SCHEMA todrop;
ALTER TABLE bountymessage SET SCHEMA todrop;
ALTER TABLE bountysubscription SET SCHEMA todrop;
ALTER TABLE bugpackageinfestation SET SCHEMA todrop;
ALTER TABLE bugproductinfestation SET SCHEMA todrop;
ALTER TABLE distributionbounty SET SCHEMA todrop;
ALTER TABLE distrocomponentuploader SET SCHEMA todrop;
ALTER TABLE mailinglistban SET SCHEMA todrop;
ALTER TABLE mentoringoffer SET SCHEMA todrop;
ALTER TABLE openidassociation SET SCHEMA todrop;
ALTER TABLE packagebugsupervisor SET SCHEMA todrop;
ALTER TABLE packageselection SET SCHEMA todrop;
ALTER TABLE posubscription SET SCHEMA todrop;
ALTER TABLE productbounty SET SCHEMA todrop;
ALTER TABLE productcvsmodule SET SCHEMA todrop;
ALTER TABLE productseriescodeimport SET SCHEMA todrop;
ALTER TABLE productsvnmodule SET SCHEMA todrop;
ALTER TABLE projectbounty SET SCHEMA todrop;
ALTER TABLE projectrelationship SET SCHEMA todrop;
ALTER TABLE pushmirroraccess SET SCHEMA todrop;
ALTER TABLE requestedcds SET SCHEMA todrop;
ALTER TABLE shipitreport SET SCHEMA todrop;
ALTER TABLE shipitsurvey SET SCHEMA todrop;
ALTER TABLE shipitsurveyanswer SET SCHEMA todrop;
ALTER TABLE shipitsurveyquestion SET SCHEMA todrop;
ALTER TABLE shipitsurveyresult SET SCHEMA todrop;
ALTER TABLE shipment SET SCHEMA todrop;
ALTER TABLE shippingrequest SET SCHEMA todrop;
ALTER TABLE shippingrun SET SCHEMA todrop;
ALTER TABLE standardshipitrequest SET SCHEMA todrop;
ALTER TABLE webserviceban SET SCHEMA todrop;
ALTER TABLE openidrpconfig SET SCHEMA todrop;
ALTER TABLE openidrpsummary SET SCHEMA todrop;
ALTER TABLE staticdiff SET SCHEMA todrop;
ALTER TABLE pocomment SET SCHEMA todrop;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 83, 2);
