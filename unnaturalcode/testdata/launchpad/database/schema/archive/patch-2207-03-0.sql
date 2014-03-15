SET client_min_messages=ERROR;

ALTER TABLE ProductSeries
    DROP COLUMN importstatus;

ALTER TABLE ProductSeries
    DROP COLUMN datelastsynced;

ALTER TABLE ProductSeries
    DROP COLUMN syncinterval;

ALTER TABLE ProductSeries
    DROP COLUMN rcstype;

ALTER TABLE ProductSeries
    DROP COLUMN cvsroot;

ALTER TABLE ProductSeries
    DROP COLUMN cvsmodule;

ALTER TABLE ProductSeries
    DROP COLUMN cvsbranch;

ALTER TABLE ProductSeries
    DROP COLUMN cvstarfileurl;

ALTER TABLE ProductSeries
    DROP COLUMN svnrepository;

ALTER TABLE ProductSeries
    DROP COLUMN dateautotested;

ALTER TABLE ProductSeries
    DROP COLUMN dateprocessapproved;

ALTER TABLE ProductSeries
    DROP COLUMN datesyncapproved;

ALTER TABLE ProductSeries
    DROP COLUMN datestarted;

ALTER TABLE ProductSeries
    DROP COLUMN datefinished;

ALTER TABLE ProductSeries
    DROP COLUMN date_published_sync;

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 3, 0);
