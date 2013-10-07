SET client_min_messages=ERROR;

CREATE TABLE BinaryPackageReleaseDownloadCount (
    id serial PRIMARY KEY,
    archive integer NOT NULL REFERENCES Archive,
    binary_package_release integer NOT NULL REFERENCES BinaryPackageRelease,
    day date NOT NULL,
    country integer REFERENCES Country,
    count integer NOT NULL
);

ALTER TABLE BinaryPackageReleaseDownloadCount ADD CONSTRAINT binarypackagereleasedownloadcount__archive__binary_package_release__day__country__key
     UNIQUE (archive, binary_package_release, day, country);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 36, 0);
