SET client_min_messages=ERROR;

CREATE TABLE SuggestivePOTemplate(potemplate integer PRIMARY KEY);

INSERT INTO SuggestivePOTemplate (
    SELECT POTemplate.id
    FROM POTemplate
    LEFT JOIN DistroSeries ON DistroSeries.id = POTemplate.distroseries
    LEFT JOIN Distribution ON Distribution.id = DistroSeries.distribution
    LEFT JOIN ProductSeries ON ProductSeries.id = POTemplate.productseries
    LEFT JOIN Product ON Product.id = ProductSeries.product
    WHERE
	POTemplate.iscurrent AND
        (Distribution.official_rosetta OR Product.official_rosetta)
    ORDER BY POTemplate.id
);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 74, 0);
