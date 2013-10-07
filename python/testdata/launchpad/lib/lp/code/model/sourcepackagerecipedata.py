# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation of the recipe storage.

This is purely an implementation detail of SourcePackageRecipe.recipe_data and
SourcePackageRecipeBuild.manifest, the classes in this file have no public
interfaces.
"""

__metaclass__ = type
__all__ = ['SourcePackageRecipeData']

from itertools import groupby

from bzrlib.plugins.builder.recipe import (
    BaseRecipeBranch,
    MergeInstruction,
    NestInstruction,
    NestPartInstruction,
    RecipeBranch,
    RecipeParser,
    SAFE_INSTRUCTIONS,
    )
from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from storm.expr import Union
from storm.locals import (
    And,
    Int,
    Reference,
    ReferenceSet,
    Select,
    Store,
    Storm,
    Unicode,
    )
from zope.component import getUtility

from lp.code.errors import (
    NoSuchBranch,
    PrivateBranchRecipe,
    TooNewRecipeFormat,
    )
from lp.code.interfaces.branchlookup import IBranchLookup
from lp.code.model.branch import Branch
from lp.services.database.bulk import (
    load_referencing,
    load_related,
    )
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.propertycache import (
    cachedproperty,
    clear_property_cache,
    get_property_cache,
    )


class InstructionType(DBEnumeratedType):
    """The instruction type, for _SourcePackageRecipeDataInstruction.type."""

    MERGE = DBItem(1, """
        Merge instruction

        A merge instruction.""")

    NEST = DBItem(2, """
        Nest instruction

        A nest instruction.""")

    NEST_PART = DBItem(3, """
        Nest-part instruction

        A nest-part instruction.""")


class _SourcePackageRecipeDataInstruction(Storm):
    """A single line from a recipe."""

    __storm_table__ = "SourcePackageRecipeDataInstruction"

    def __init__(self, name, type, comment, line_number, branch, revspec,
                 directory, recipe_data, parent_instruction,
                 source_directory):
        super(_SourcePackageRecipeDataInstruction, self).__init__()
        self.name = unicode(name)
        self.type = type
        self.comment = comment
        self.line_number = line_number
        self.branch = branch
        if revspec is not None:
            revspec = unicode(revspec)
        self.revspec = revspec
        if directory is not None:
            directory = unicode(directory)
        self.directory = directory
        self.source_directory = source_directory
        self.recipe_data = recipe_data
        self.parent_instruction = parent_instruction

    id = Int(primary=True)

    name = Unicode(allow_none=False)
    type = EnumCol(notNull=True, schema=InstructionType)
    comment = Unicode(allow_none=True)
    line_number = Int(allow_none=False)

    branch_id = Int(name='branch', allow_none=False)
    branch = Reference(branch_id, 'Branch.id')

    revspec = Unicode(allow_none=True)
    directory = Unicode(allow_none=True)
    source_directory = Unicode(allow_none=True)

    recipe_data_id = Int(name='recipe_data', allow_none=False)
    recipe_data = Reference(recipe_data_id, 'SourcePackageRecipeData.id')

    parent_instruction_id = Int(name='parent_instruction', allow_none=True)
    parent_instruction = Reference(
        parent_instruction_id, '_SourcePackageRecipeDataInstruction.id')

    def appendToRecipe(self, recipe_branch):
        """Append a bzr-builder instruction to the recipe_branch object."""
        branch = RecipeBranch(
            self.name, self.branch.bzr_identity, self.revspec)
        if self.type == InstructionType.MERGE:
            recipe_branch.merge_branch(branch)
        elif self.type == InstructionType.NEST:
            recipe_branch.nest_branch(self.directory, branch)
        elif self.type == InstructionType.NEST_PART:
            recipe_branch.nest_part_branch(
                branch, self.source_directory, self.directory)
        else:
            raise AssertionError("Unknown type %r" % self.type)
        return branch


MAX_RECIPE_FORMAT = 0.4


class SourcePackageRecipeData(Storm):
    """The database representation of a BaseRecipeBranch from bzr-builder.

    This is referenced from the SourcePackageRecipe table as the 'recipe_data'
    column and from the SourcePackageRecipeBuild table as the 'manifest'
    column.
    """

    __storm_table__ = "SourcePackageRecipeData"

    id = Int(primary=True)

    base_branch_id = Int(name='base_branch', allow_none=False)
    base_branch = Reference(base_branch_id, 'Branch.id')

    recipe_format = Unicode(allow_none=False)
    deb_version_template = Unicode(allow_none=True)
    revspec = Unicode(allow_none=True)

    instructions = ReferenceSet(
        id, _SourcePackageRecipeDataInstruction.recipe_data_id,
        order_by=_SourcePackageRecipeDataInstruction.line_number)

    sourcepackage_recipe_id = Int(
        name='sourcepackage_recipe', allow_none=True)
    sourcepackage_recipe = Reference(
        sourcepackage_recipe_id, 'SourcePackageRecipe.id')

    sourcepackage_recipe_build_id = Int(
        name='sourcepackage_recipe_build', allow_none=True)
    sourcepackage_recipe_build = Reference(
        sourcepackage_recipe_build_id, 'SourcePackageRecipeBuild.id')

    @staticmethod
    def getParsedRecipe(recipe_text):
        parser = RecipeParser(recipe_text)
        return parser.parse(permitted_instructions=SAFE_INSTRUCTIONS)

    @staticmethod
    def findRecipes(branch):
        from lp.code.model.sourcepackagerecipe import SourcePackageRecipe
        store = Store.of(branch)
        return store.find(
            SourcePackageRecipe,
            SourcePackageRecipe.id.is_in(Union(
                Select(
                    SourcePackageRecipeData.sourcepackage_recipe_id,
                    SourcePackageRecipeData.base_branch == branch),
                Select(
                    SourcePackageRecipeData.sourcepackage_recipe_id,
                    And(
                        _SourcePackageRecipeDataInstruction.recipe_data_id ==
                        SourcePackageRecipeData.id,
                        _SourcePackageRecipeDataInstruction.branch == branch)
                    )
            ))
        )

    @classmethod
    def createManifestFromText(cls, text, sourcepackage_recipe_build):
        """Create a manifest for the specified build.

        :param text: The text of the recipe to create a manifest for.
        :param sourcepackage_recipe_build: The build to associate the manifest
            with.
        :return: an instance of SourcePackageRecipeData.
        """
        parsed = cls.getParsedRecipe(text)
        return cls(
            parsed, sourcepackage_recipe_build=sourcepackage_recipe_build)

    def getRecipe(self):
        """The BaseRecipeBranch version of the recipe."""
        base_branch = BaseRecipeBranch(
            self.base_branch.bzr_identity, self.deb_version_template,
            self.recipe_format, self.revspec)
        insn_stack = []
        for insn in self.instructions:
            while insn_stack and \
                      insn_stack[-1]['insn'] != insn.parent_instruction:
                insn_stack.pop()
            if insn_stack:
                target_branch = insn_stack[-1]['recipe_branch']
            else:
                target_branch = base_branch
            recipe_branch = insn.appendToRecipe(target_branch)
            insn_stack.append(
                dict(insn=insn, recipe_branch=recipe_branch))
        return base_branch

    def _scanInstructions(self, recipe_branch):
        """Check the recipe_branch doesn't use 'run' and look up the branches.

        We do all the lookups before we start constructing database objects to
        avoid flushing half-constructed objects to the database.

        :return: A map ``{branch_url: db_branch}``.
        """
        r = {}
        for instruction in recipe_branch.child_branches:
            db_branch = getUtility(IBranchLookup).getByUrl(
                instruction.recipe_branch.url)
            if db_branch is None:
                raise NoSuchBranch(instruction.recipe_branch.url)
            if db_branch.private:
                raise PrivateBranchRecipe(db_branch)
            r[instruction.recipe_branch.url] = db_branch
            r.update(self._scanInstructions(instruction.recipe_branch))
        return r

    def _recordInstructions(self, recipe_branch, parent_insn, branch_map,
                            line_number=0):
        """Build _SourcePackageRecipeDataInstructions for the recipe_branch.
        """
        for instruction in recipe_branch.child_branches:
            nest_path = instruction.nest_path
            source_directory = None
            if isinstance(instruction, MergeInstruction):
                type = InstructionType.MERGE
            elif isinstance(instruction, NestInstruction):
                type = InstructionType.NEST
            elif isinstance(instruction, NestPartInstruction):
                type = InstructionType.NEST_PART
                nest_path = instruction.target_subdir
                source_directory = instruction.subpath
            else:
                # Unsupported instructions should have been filtered out by
                # _scanInstructions; if we get surprised here, that's a bug.
                raise AssertionError(
                    "Unsupported instruction %r" % instruction)
            line_number += 1
            comment = None
            db_branch = branch_map[instruction.recipe_branch.url]
            insn = _SourcePackageRecipeDataInstruction(
                instruction.recipe_branch.name, type, comment,
                line_number, db_branch, instruction.recipe_branch.revspec,
                nest_path, self, parent_insn, source_directory)
            line_number = self._recordInstructions(
                instruction.recipe_branch, insn, branch_map, line_number)
        return line_number

    def setRecipe(self, builder_recipe):
        """Convert the BaseRecipeBranch `builder_recipe` to the db form."""
        clear_property_cache(self)
        if builder_recipe.format > MAX_RECIPE_FORMAT:
            raise TooNewRecipeFormat(builder_recipe.format, MAX_RECIPE_FORMAT)
        branch_map = self._scanInstructions(builder_recipe)
        # If this object hasn't been added to a store yet, there can't be any
        # instructions linking to us yet.
        if Store.of(self) is not None:
            self.instructions.find().remove()
        branch_lookup = getUtility(IBranchLookup)
        base_branch = branch_lookup.getByUrl(builder_recipe.url)
        if base_branch is None:
            raise NoSuchBranch(builder_recipe.url)
        if base_branch.private:
            raise PrivateBranchRecipe(base_branch)
        if builder_recipe.revspec is not None:
            self.revspec = unicode(builder_recipe.revspec)
        else:
            self.revspec = None
        self._recordInstructions(
            builder_recipe, parent_insn=None, branch_map=branch_map)
        self.base_branch = base_branch
        if builder_recipe.deb_version is None:
            self.deb_version_template = None
        else:
            self.deb_version_template = unicode(builder_recipe.deb_version)
        self.recipe_format = unicode(builder_recipe.format)

    def __init__(self, recipe, sourcepackage_recipe=None,
                 sourcepackage_recipe_build=None):
        """Initialize from the bzr-builder recipe and link it to a db recipe.
        """
        super(SourcePackageRecipeData, self).__init__()
        self.setRecipe(recipe)
        self.sourcepackage_recipe = sourcepackage_recipe
        self.sourcepackage_recipe_build = sourcepackage_recipe_build

    @staticmethod
    def preLoadReferencedBranches(sourcepackagerecipedatas):
        # Load the related Branch, _SourcePackageRecipeDataInstruction.
        load_related(
            Branch, sourcepackagerecipedatas, ['base_branch_id'])
        sprd_instructions = load_referencing(
            _SourcePackageRecipeDataInstruction,
            sourcepackagerecipedatas, ['recipe_data_id'])
        sub_branches = load_related(
            Branch, sprd_instructions, ['branch_id'])
        # Store the pre-fetched objects on the sourcepackagerecipedatas
        # objects.
        branch_to_recipe_data = dict([
            (instr.branch_id, instr.recipe_data_id)
                for instr in sprd_instructions])
        caches = dict((sprd.id, [sprd, get_property_cache(sprd)])
            for sprd in sourcepackagerecipedatas)
        for unused, [sprd, cache] in caches.items():
            cache._referenced_branches = [sprd.base_branch]
        for recipe_data_id, branches in groupby(
            sub_branches, lambda branch: branch_to_recipe_data[branch.id]):
            cache = caches[recipe_data_id][1]
            cache._referenced_branches.extend(list(branches))

    def getReferencedBranches(self):
        """Return an iterator of the Branch objects referenced by this recipe.
        """
        return self._referenced_branches

    @cachedproperty
    def _referenced_branches(self):
        referenced_branches = [self.base_branch]
        sub_branches = IStore(self).find(
            Branch,
            _SourcePackageRecipeDataInstruction.recipe_data == self,
            Branch.id == _SourcePackageRecipeDataInstruction.branch_id)
        referenced_branches.extend(sub_branches)
        return referenced_branches
