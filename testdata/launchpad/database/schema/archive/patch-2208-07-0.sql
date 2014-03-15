SET client_min_messages=ERROR;

CREATE TABLE DistroSeriesDifference (
    id serial PRIMARY KEY,
    derived_series integer NOT NULL CONSTRAINT distroseriesdifference__derived_series__fk REFERENCES distroseries,
    source_package_name integer NOT NULL CONSTRAINT distroseriesdifference__source_package_name__fk REFERENCES sourcepackagename,
    package_diff integer CONSTRAINT distroseriesdifference__package_diff__fk REFERENCES packagediff,
    status integer NOT NULL,
    difference_type integer NOT NULL
);
CREATE INDEX distroseriesdifference__derived_series__idx ON distroseriesdifference(derived_series);
CREATE INDEX distroseriesdifference__source_package_name__idx ON distroseriesdifference(source_package_name);
CREATE INDEX distroseriesdifference__status__idx ON distroseriesdifference(status);
CREATE INDEX distroseriesdifference__difference_type__idx ON distroseriesdifference(difference_type);
CREATE INDEX distroseriesdifference__package_diff__idx ON distroseriesdifference(package_diff);

CREATE TABLE DistroSeriesDifferenceMessage(
    id serial PRIMARY KEY,
    distro_series_difference integer NOT NULL CONSTRAINT distroseriesdifferencemessage__distro_series_difference__fk REFERENCES distroseriesdifference,
    message integer NOT NULL CONSTRAINT distroseriesdifferencemessage__message__fk REFERENCES message UNIQUE
);
CREATE INDEX distroseriesdifferencemessage__distroseriesdifference__idx ON distroseriesdifferencemessage(distro_series_difference);

INSERT INTO LaunchpadDatabaseRevision VALUES (2208, 07, 0);
