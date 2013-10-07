SET client_min_messages = ERROR;

CREATE INDEX archive__fti__idx ON archive USING GIN (fti);
CREATE INDEX message__fti__idx ON message USING GIN (fti);
CREATE INDEX faq__fti__idx ON faq USING GIN (fti);
CREATE INDEX question__fti__idx ON question USING GIN (fti);
CREATE INDEX binarypackagerelease__fti__idx
    ON binarypackagerelease USING GIN (fti);
CREATE INDEX distroseriespackagecache__fti__idx
    ON distroseriespackagecache USING GIN (fti);
CREATE INDEX specification__fti__idx ON specification USING GIN (fti);
CREATE INDEX messagechunk__fti__idx ON messagechunk USING GIN (fti);
CREATE INDEX project__fti__idx ON project USING GIN (fti);
CREATE INDEX cve__fti__idx ON cve USING GIN (fti);
CREATE INDEX person__fti__idx ON person USING GIN (fti);
CREATE INDEX bug__fti__idx ON bug USING GIN (fti);
CREATE INDEX distributionsourcepackagecache__fti__idx
    ON distributionsourcepackagecache USING GIN (fti);
CREATE INDEX productreleasefile__fti__idx
    ON productreleasefile USING GIN (fti);
CREATE INDEX product__fti__idx ON product USING GIN (fti);
CREATE INDEX distribution__fti__idx ON distribution USING GIN (fti);

INSERT INTO LaunchpadDatabaseRevision VALUES (2209, 21, 2);
