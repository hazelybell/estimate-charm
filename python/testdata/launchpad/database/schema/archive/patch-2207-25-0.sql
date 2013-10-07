SET client_min_messages=ERROR;

CREATE TABLE SourcePackageRecipe (
    id serial PRIMARY KEY,
    date_created timestamp without time zone DEFAULT timezone('UTC'::text, now()) NOT NULL,
    date_last_modified timestamp without time zone DEFAULT timezone('UTC'::text, now()) NOT NULL,
    registrant integer NOT NULL REFERENCES Person,
    owner integer NOT NULL REFERENCES Person,
    distroseries integer NOT NULL REFERENCES DistroSeries,
    sourcepackagename integer NOT NULL REFERENCES SourcePackageName,
    name text NOT NULL
);

ALTER TABLE SourcePackageRecipe ADD CONSTRAINT sourcepackagerecipe__owner__distroseries__sourcepackagename__name__key
     UNIQUE (owner, distroseries, sourcepackagename, name);

CREATE TABLE SourcePackageRecipeBuild (
    id serial PRIMARY KEY,
    -- most of this is just copied from Build

    -- I've dropped: processor, sourcepackagerelease, pocket, dependencies
    -- changed: distroarchseries to distroseries
    -- added: recipe and manifest
    date_created timestamp without time zone DEFAULT timezone('UTC'::text, ('now'::text)::timestamp(6) with time zone) NOT NULL,
    distroseries integer NOT NULL REFERENCES distroseries,
    sourcepackagename integer NOT NULL REFERENCES SourcePackageName,
    build_state integer NOT NULL,
    date_built timestamp without time zone,
    build_duration interval,
    build_log integer REFERENCES libraryfilealias,
    builder integer REFERENCES builder,
    date_first_dispatched timestamp without time zone,
    requester integer NOT NULL REFERENCES Person,
    recipe integer REFERENCES SourcePackageRecipe NOT NULL,
    archive integer NOT NULL REFERENCES Archive
);

CREATE TABLE SourcePackageRecipeBuildUpload (
    id serial PRIMARY KEY,
    date_created timestamp without time zone DEFAULT timezone('UTC'::text, ('now'::text)::timestamp(6) with time zone) NOT NULL,
    registrant integer NOT NULL REFERENCES Person,
    sourcepackage_recipe_build integer NOT NULL REFERENCES SourcePackageRecipeBuild,
    archive integer NOT NULL REFERENCES Archive,
    upload_log integer REFERENCES LibraryFileAlias,
    state integer NOT NULL -- an enum, WAITING/UPLOADED/FAILED or something like that.
);

-- indexes for SourcePackageRecipeBuildUpload I guess

ALTER TABLE SourcePackageRelease
  ADD COLUMN sourcepackage_recipe_build integer REFERENCES SourcePackageRecipeBuild;

CREATE TABLE SourcePackageRecipeBuildJob (
    id serial PRIMARY KEY,
    job integer NOT NULL REFERENCES Job,
    sourcepackage_recipe_build integer REFERENCES SourcePackageRecipeBuild
);

ALTER TABLE SourcePackageRecipeBuildJob ADD CONSTRAINT sourcepackagerecipebuildjob__sourcepackage_recipe_build__key
    UNIQUE (sourcepackage_recipe_build);

ALTER TABLE SourcePackageRecipeBuildJob ADD CONSTRAINT sourcepackagerecipebuildjob__job__key
    UNIQUE (job);

CREATE TABLE SourcePackageRecipeData (
    id serial PRIMARY KEY,
    base_branch integer NOT NULL REFERENCES Branch,
    recipe_format text NOT NULL,
    deb_version_template text NOT NULL,
    revspec text,
    sourcepackage_recipe integer REFERENCES SourcePackageRecipe,
    sourcepackage_recipe_build integer REFERENCES SourcePackageRecipeBuild
);

ALTER TABLE SourcePackageRecipeData ADD CONSTRAINT sourcepackagerecipedata__recipe_or_build_is_not_null
    CHECK (sourcepackage_recipe IS NULL != sourcepackage_recipe_build IS NULL);
CREATE UNIQUE INDEX sourcepackagerecipedata__sourcepackage_recipe__key
    ON SourcepackageRecipeData(sourcepackage_recipe)
 WHERE sourcepackage_recipe IS NOT NULL;
CREATE UNIQUE INDEX sourcepackagerecipedata__sourcepackage_recipe_build__key
    ON SourcepackageRecipeData(sourcepackage_recipe_build)
 WHERE sourcepackage_recipe_build IS NOT NULL;

CREATE TABLE SourcePackageRecipeDataInstruction (
    id serial PRIMARY KEY,
    name text NOT NULL,
    type integer NOT NULL, -- MERGE == 1, NEST == 2
    comment text,
    line_number integer NOT NULL,
    branch integer NOT NULL REFERENCES Branch,
    revspec text,
    directory text,
    recipe_data integer NOT NULL REFERENCES SourcePackageRecipeData,
    parent_instruction integer REFERENCES SourcePackageRecipeDataInstruction
);

ALTER TABLE SourcePackageRecipeDataInstruction ADD CONSTRAINT sourcepackagerecipedatainstruction__name__recipe_data__key
     UNIQUE (name, recipe_data);
ALTER TABLE SourcePackageRecipeDataInstruction ADD CONSTRAINT sourcepackagerecipedatainstruction__recipe_data__line_number__key
     UNIQUE (recipe_data, line_number);
ALTER TABLE SourcePackageRecipeDataInstruction ADD CONSTRAINT sourcepackagerecipedatainstruction__directory_not_null
     CHECK ((type = 1 AND directory IS NULL) OR (type = 2 AND directory IS NOT NULL));

CREATE INDEX sourcepackagerecipedata__base_branch__idx
ON SourcepackageRecipeData(base_branch);

CREATE INDEX sourcepackagerecipedatainstruction__branch__idx
ON SourcepackageRecipeDataInstruction(branch);

CREATE INDEX sourcepackagerecipe__registrant__idx
ON SourcepackageRecipe(registrant);

--CREATE INDEX sourcepackagerecipe__owner__idx
--ON SourcepackageRecipe(owner);

CREATE INDEX sourcepackagerecipebuild__distroseries__idx
ON SourcepackageRecipeBuild(distroseries);

CREATE INDEX sourcepackagerecipebuild__sourcepackagename__idx
ON SourcepackageRecipeBuild(sourcepackagename);

CREATE INDEX sourcepackagerecipebuild__build_log__idx
ON SourcepackageRecipeBuild(build_log) WHERE build_log IS NOT NULL;

CREATE INDEX sourcepackagerecipebuild__builder__idx
ON SourcepackageRecipeBuild(builder);

CREATE INDEX sourcepackagerecipebuild__requester__idx
ON SourcepackageRecipeBuild(requester);

CREATE INDEX sourcepackagerecipebuild__recipe__idx
ON SourcepackageRecipeBuild(recipe);

CREATE INDEX sourcepackagerecipebuild__archive__idx
ON SourcepackageRecipeBuild(archive);

CREATE INDEX sourcepackagebuildupload__registrant__idx
ON SourcepackageRecipeBuildUpload(registrant);

CREATE INDEX sourcepackagerecipebuildupload__archive__idx
ON SourcepackageRecipeBuildUpload(archive);

CREATE INDEX sourcepackagerecipebuildupload__upload_log__idx
ON SourcepackageRecipeBuildUpload(upload_log) WHERE upload_log IS NOT NULL;

CREATE INDEX sourcepackagerelease__sourcepackage_recipe_build__idx
ON SourcepackageRelease(sourcepackage_recipe_build);

INSERT INTO LaunchpadDatabaseRevision VALUES (2207, 25, 0);
