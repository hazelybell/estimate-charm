-- Copyright 2011 Canonical Ltd.  This software is licensed under the
-- GNU Affero General Public License version 3 (see the file LICENSE).

SET client_min_messages=ERROR;

-- Before we remove unwanted StructuralSubscription rows, we can tweak
-- some foreign key constraints to make this removal easier.
-- StructuralSubscription is referenced by BugSubscriptionFilter
-- BugSubscriptionFilter is referenced too by BugNotificationFilter, but
-- that relationship is already ON DELETE CASCADE.
ALTER TABLE BugSubscriptionFilter
    DROP CONSTRAINT bugsubscriptionfilter_structuralsubscription_fkey,
    ADD CONSTRAINT bugsubscriptionfilter__structuralsubscription__fk
        FOREIGN KEY (structuralsubscription)
        REFERENCES StructuralSubscription ON DELETE CASCADE;


-- WHAT ARE WE DOING? -----------------------------------------------------

-- These three errors have been observed, and are corrected here.

-- If StructuralSubscription.product is not NULL, the combination of
-- StructuralSubscription.product and StructuralSubscription.subscriber
-- should be unique.

-- If StructuralSubscription.project is not NULL, the combination of
-- StructuralSubscription.project and StructuralSubscription.subscriber
-- should be unique.

-- If StructuralSubscription.distribution and
-- StructuralSubscription.sourcepackagename are not NULL, the combination of
-- StructuralSubscription.distribution,
-- StructuralSubscription.sourcepackagename, and
-- StructuralSubscription.subscriber should be unique.

-- These have not been observed, but are prevented for safekeeping.

-- If StructuralSubscription.distribution is not NULL but
-- StructuralSubscription.sourcepackagename is NULL, the combination of
-- StructuralSubscription.distribution and
-- StructuralSubscription.subscriber should be unique.

-- If StructuralSubscription.distroseries is not NULL, the combination of
-- StructuralSubscription.distroseries and StructuralSubscription.subscriber
-- should be unique.

-- If StructuralSubscription.milestone is not NULL, the combination of
-- StructuralSubscription.milestone and StructuralSubscription.subscriber
-- should be unique.

-- If StructuralSubscription.productseries is not NULL, the combination of
-- StructuralSubscription.productseries and StructuralSubscription.subscriber
-- should be unique.

-- So, we want to eliminate dupes, and then set up constraints so they do not
-- come back.

-- ELIMINATE DUPES --------------------------------------------------------

-- First, we eliminate dupes.

-- We find duplicates and eliminate the ones that are older (on the basis
-- of the id being a smaller number).

-- This eliminates product dupes.  As an example, this is run on staging.

-- lpmain_staging=> SELECT Subscription.product,
--        Subscription.subscriber,
--        Subscription.id
-- FROM StructuralSubscription AS Subscription
-- WHERE EXISTS (
--    SELECT StructuralSubscription.product, StructuralSubscription.subscriber
--    FROM StructuralSubscription
--    WHERE
--        StructuralSubscription.product = Subscription.product
--        AND StructuralSubscription.subscriber = Subscription.subscriber
--    GROUP BY StructuralSubscription.product,
--             StructuralSubscription.subscriber
--    HAVING Count(*)>1)
--    ORDER BY Subscription.product, Subscription.subscriber, Subscription.id;
--  product | subscriber |  id   
-- ---------+------------+-------
--     2461 |    2212151 |  7570
--     2461 |    2212151 |  7571
--     7533 |    1814750 |  5428
--     7533 |    1814750 |  5492
--     7534 |    1814750 |  5429
--     7534 |    1814750 |  5491
--     8269 |     242763 |  8191
--     8269 |     242763 |  8192
--     9868 |    3388985 | 25131
--     9868 |    3388985 | 25132
--    24395 |    3391740 | 21770
--    24395 |    3391740 | 23900
-- (12 rows)
-- 
-- lpmain_staging=> WITH duped_values AS
--     (SELECT Subscription.product,
--             Subscription.subscriber,
--             Subscription.id
--      FROM StructuralSubscription AS Subscription
--      WHERE EXISTS (                                                        
--         SELECT StructuralSubscription.product,
--                StructuralSubscription.subscriber
--         FROM StructuralSubscription
--         WHERE                                               
--             StructuralSubscription.product = Subscription.product
--             AND StructuralSubscription.subscriber = Subscription.subscriber
--         GROUP BY StructuralSubscription.product,
--                  StructuralSubscription.subscriber
--         HAVING Count(*)>1))
--  SELECT duped_values.id
--  FROM duped_values
--  WHERE duped_values.id NOT IN
--     (SELECT MAX(duped_values.id)
--      FROM duped_values
--      GROUP BY duped_values.product, duped_values.subscriber);
--   id   
-- -------
--   5429
--   5428
--   8191
--  25131
--   7570
--  21770
-- (6 rows)

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.product,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.product,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.product = Subscription.product
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.product,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.product, duped_values.subscriber));

-- Now we eliminate project dupes.  This, like most of the variations,
-- is a copy-and-paste job, replacing "product" with "project".

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.project,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.project,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.project = Subscription.project
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.project,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.project, duped_values.subscriber));

-- Now we eliminate distroseries dupes.  They don't exist on staging, but
-- there's nothing keeping them from happening, so this is just to make sure.
-- This is another copy and paste job.

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.distroseries,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.distroseries,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.distroseries = Subscription.distroseries
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.distroseries,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.distroseries, duped_values.subscriber));

-- Now we eliminate milestone dupes.  This again does not have matches on
-- staging, and is again a copy-and-paste job.

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.milestone,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.milestone,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.milestone = Subscription.milestone
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.milestone,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.milestone, duped_values.subscriber));

-- Now we eliminate productseries dupes.  This again does not have matches on
-- staging, and is again a copy-and-paste job.

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.productseries,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.productseries,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.productseries = Subscription.productseries
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.productseries,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.productseries, duped_values.subscriber));

-- Now we need to eliminate distribution and sourcepackagename dupes.  These
-- involve a bit more modification of the pattern, though it is still the
-- same basic idea.

-- This is the distribution.  It has no matches on staging.

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.distribution,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.distribution,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.distribution = Subscription.distribution
                    AND StructuralSubscription.subscriber = Subscription.subscriber
-- These are the two new lines.
                    AND StructuralSubscription.sourcepackagename IS NULL
                    AND Subscription.sourcepackagename IS NULL
                GROUP BY StructuralSubscription.distribution,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.distribution, duped_values.subscriber));

-- This is the sourcepackagename.  It *does* have matches on staging.

DELETE FROM StructuralSubscription WHERE
    StructuralSubscription.id IN 
        (WITH duped_values AS
            (SELECT Subscription.distribution,
                    Subscription.sourcepackagename,
                    Subscription.subscriber,
                    Subscription.id
             FROM StructuralSubscription AS Subscription
             WHERE EXISTS (
                SELECT StructuralSubscription.distribution,
                       StructuralSubscription.sourcepackagename,
                       StructuralSubscription.subscriber
                FROM StructuralSubscription
                WHERE
                    StructuralSubscription.distribution = Subscription.distribution
                    AND StructuralSubscription.sourcepackagename = Subscription.sourcepackagename
                    AND StructuralSubscription.subscriber = Subscription.subscriber
                GROUP BY StructuralSubscription.distribution,
                         StructuralSubscription.sourcepackagename,
                         StructuralSubscription.subscriber
                HAVING Count(*)>1))
         SELECT duped_values.id
         FROM duped_values
         WHERE duped_values.id NOT IN
            (SELECT MAX(duped_values.id)
             FROM duped_values
             GROUP BY duped_values.distribution,
                      duped_values.sourcepackagename,
                      duped_values.subscriber));


-- CREATE CONSTRAINTS ----------------------------------------------------

CREATE UNIQUE INDEX structuralsubscription__product__subscriber__key
ON StructuralSubscription(product, subscriber) WHERE product IS NOT NULL;

CREATE UNIQUE INDEX structuralsubscription__project__subscriber__key
ON StructuralSubscription(project, subscriber) WHERE project IS NOT NULL;

-- This represents a subscription to a sourcepackage within a distribution.
CREATE UNIQUE INDEX
    structuralsubscription__distribution__sourcepackagename__subscriber__key
ON StructuralSubscription(distribution, sourcepackagename, subscriber)
WHERE distribution IS NOT NULL AND sourcepackagename IS NOT NULL;

-- This represents a subscription to an entire distribution.  Even though this
-- kind of distribution subsumes a sourcepackage distrubution (above), the
-- configuration may be very different, so they are not necessarily redundant.
CREATE UNIQUE INDEX structuralsubscription__distribution__subscriber__key
ON StructuralSubscription(distribution, subscriber)
WHERE distribution IS NOT NULL AND sourcepackagename IS NULL;

CREATE UNIQUE INDEX structuralsubscription__distroseries__subscriber__key
ON StructuralSubscription(distroseries, subscriber)
WHERE distroseries IS NOT NULL;

-- NB. Currently we can't subscribe to a (distroseries, sourcepackagename)
-- so no need for the second partial distroseries index like the two
-- distribution indexes.

CREATE UNIQUE INDEX structuralsubscription__milestone__subscriber__key
ON StructuralSubscription(milestone, subscriber)
WHERE milestone IS NOT NULL;

CREATE UNIQUE INDEX structuralsubscription__productseries__subscriber__key
ON StructuralSubscription(productseries, subscriber)
WHERE productseries IS NOT NULL;

-- Drop obsolete indexes - the above constraints make them redundant.
DROP INDEX structuralsubscription__distribution__sourcepackagename__idx;
DROP INDEX structuralsubscription__distroseries__idx;
DROP INDEX structuralsubscription__milestone__idx;
DROP INDEX structuralsubscription__product__idx;
DROP INDEX structuralsubscription__productseries__idx;
DROP INDEX structuralsubscription__project__idx;

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 65, 0);
