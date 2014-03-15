SET client_min_messages=ERROR;

ALTER TABLE EmailAddress ADD CONSTRAINT emailaddress__person__fk
    FOREIGN KEY (person) REFERENCES Person;

CREATE TEMPORARY TABLE DudAccountLinks AS
SELECT Person.id
FROM Person
LEFT OUTER JOIN Account ON Person.account = Account.id
WHERE Person.account IS NOT NULL AND Account.id IS NULL;

UPDATE Person SET account = NULL
FROM DudAccountLinks
WHERE Person.id = DudAccountLinks.id;

DROP TABLE DudAccountLinks;

ALTER TABLE Person ADD CONSTRAINT person__account__fk
    FOREIGN KEY (account) REFERENCES Account;

ALTER TABLE MailingListSubscription
    ADD CONSTRAINT mailinglistsubscription__email_address_fk
    FOREIGN KEY (email_address) REFERENCES EmailAddress
    ON DELETE CASCADE;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 48, 0);

