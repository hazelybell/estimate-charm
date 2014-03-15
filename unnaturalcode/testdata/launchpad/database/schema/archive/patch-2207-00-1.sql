SET client_min_messages=ERROR;

-- Remove an incorrect index
DROP INDEX question__owner__idx;

-- All columns referencing Person.id need an index to ensure
-- Person merge and Person removal runs as fast as possible.
CREATE INDEX bounty__claimant__idx ON bounty (claimant);
CREATE INDEX bounty__owner__idx ON bounty (owner);
CREATE INDEX bounty__reviewer__idx ON bounty (reviewer);
CREATE INDEX branchmergeproposal__registrant__idx ON branchmergeproposal (registrant);
CREATE INDEX bugnotificationrecipient__person__idx ON bugnotificationrecipient (person);
CREATE INDEX bugpackageinfestation__creator__idx ON bugpackageinfestation (creator);
CREATE INDEX bugpackageinfestation__lastmodifiedby__idx ON bugpackageinfestation (lastmodifiedby);
CREATE INDEX bugpackageinfestation__verifiedby__idx ON bugpackageinfestation (verifiedby);
CREATE INDEX bugproductinfestation__creator__idx ON bugproductinfestation (creator);
CREATE INDEX bugproductinfestation__lastmodifiedby__idx ON bugproductinfestation (lastmodifiedby);
CREATE INDEX bugproductinfestation__verifiedby__idx ON bugproductinfestation (verifiedby);
CREATE INDEX builder__owner__idx ON builder (owner);
CREATE INDEX distribution__driver__idx ON distribution (driver);
CREATE INDEX distribution__members__idx ON distribution (members);
CREATE INDEX distribution__mirror_admin__idx ON distribution (mirror_admin);
CREATE INDEX distribution__owner__idx ON distribution (owner);
CREATE INDEX distribution__security_contact__idx ON distribution (security_contact);
CREATE INDEX distribution__upload_admin__idx ON distribution (upload_admin);
CREATE INDEX distributionmirror__owner__idx ON distributionmirror (owner);
CREATE INDEX distributionmirror__reviewer__idx ON distributionmirror (reviewer);
CREATE INDEX faq__last_updated_by__idx ON faq (last_updated_by);
CREATE INDEX faq__owner__idx ON faq (owner);
CREATE INDEX mirror__owner__idx ON mirror (owner);
CREATE INDEX packaging__owner__idx ON packaging (owner);
CREATE INDEX person__registrant__idx ON person (registrant);
CREATE INDEX personlocation__last_modified_by__idx ON personlocation (last_modified_by);
CREATE INDEX poexportrequest__person__idx ON poexportrequest (person);
CREATE INDEX productseries__driver__idx ON productseries (driver);
CREATE INDEX productseries__owner__idx ON productseries (owner);
CREATE INDEX project__driver__idx ON project (driver);
CREATE INDEX question__owner__idx ON question (owner);
CREATE INDEX sprint__owner__idx ON sprint (owner);
CREATE INDEX teammembership__team__idx ON teammembership (team);
CREATE INDEX translationgroup__owner__idx ON translationgroup (owner);
CREATE INDEX translator__translator__idx ON translator (translator);
CREATE INDEX vote__person__idx ON vote (person);

-- References to LibraryFileAlias need indexes to ensure the librarian
-- garbage collector runs efficiently.
CREATE INDEX branchmergeproposal__merge_log_file__idx ON branchmergeproposal (merge_log_file);
CREATE INDEX codeimportresult__log_file__idx ON codeimportresult (log_file);
CREATE INDEX pocketchroot__chroot__idx ON pocketchroot (chroot);
CREATE INDEX productreleasefile__libraryfile__idx ON productreleasefile (libraryfile);
CREATE INDEX shipitreport__csvfile__idx ON shipitreport (csvfile);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 00, 1);

