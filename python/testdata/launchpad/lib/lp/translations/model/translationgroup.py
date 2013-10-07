# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'TranslationGroup',
    'TranslationGroupSet',
    ]

import operator

from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    SQLObjectNotFound,
    SQLRelatedJoin,
    StringCol,
    )
from storm.expr import (
    Join,
    LeftJoin,
    )
from storm.store import Store
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.registry.interfaces.person import validate_public_person
from lp.registry.model.person import Person
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.constants import DEFAULT
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import (
    ISlaveStore,
    IStore,
    )
from lp.services.database.sqlbase import SQLBase
from lp.services.librarian.model import (
    LibraryFileAlias,
    LibraryFileContent,
    )
from lp.services.worlddata.model.language import Language
from lp.translations.interfaces.translationgroup import (
    ITranslationGroup,
    ITranslationGroupSet,
    )
from lp.translations.model.translator import Translator


class TranslationGroup(SQLBase):
    """A TranslationGroup."""

    implements(ITranslationGroup)

    # default to listing alphabetically
    _defaultOrder = 'name'

    # db field names
    name = StringCol(unique=True, alternateID=True, notNull=True)
    title = StringCol(notNull=True)
    summary = StringCol(notNull=True)
    datecreated = UtcDateTimeCol(notNull=True, default=DEFAULT)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    # useful joins
    distributions = SQLMultipleJoin('Distribution',
        joinColumn='translationgroup')
    languages = SQLRelatedJoin('Language', joinColumn='translationgroup',
        intermediateTable='Translator', otherColumn='language')
    translators = SQLMultipleJoin('Translator',
                                  joinColumn='translationgroup')
    translation_guide_url = StringCol(notNull=False, default=None)

    def __getitem__(self, language_code):
        """See `ITranslationGroup`."""
        query = Store.of(self).find(
            Translator,
            Translator.translationgroup == self,
            Translator.languageID == Language.id,
            Language.code == language_code)

        translator = query.one()
        if translator is None:
            raise NotFoundError(language_code)

        return translator

    # used to note additions
    def add(self, content):
        """See ITranslationGroup."""
        return content

    # adding and removing translators
    def remove_translator(self, translator):
        """See ITranslationGroup."""
        Translator.delete(translator.id)

    # get a translator by language or code
    def query_translator(self, language):
        """See ITranslationGroup."""
        return Translator.selectOneBy(language=language,
                                      translationgroup=self)

    @property
    def products(self):
        """See `ITranslationGroup`."""
        # Avoid circular imports.
        from lp.registry.model.product import Product

        return Product.selectBy(translationgroup=self.id, active=True)

    @property
    def projects(self):
        """See `ITranslationGroup`."""
        # Avoid circular imports.
        from lp.registry.model.projectgroup import ProjectGroup

        return ProjectGroup.selectBy(translationgroup=self.id, active=True)

    # A limit of projects to get for the `top_projects`.
    TOP_PROJECTS_LIMIT = 6

    @property
    def top_projects(self):
        """See `ITranslationGroup`."""
        # XXX Danilo 2009-08-25: We should make this list show a list
        # of projects based on the top translations karma (bug #418493).
        goal = self.TOP_PROJECTS_LIMIT
        projects = list(self.distributions[:goal])
        found = len(projects)
        if found < goal:
            projects.extend(
                list(self.projects[:goal-found]))
            found = len(projects)
        if found < goal:
            projects.extend(
                list(self.products[:goal-found]))
        return projects

    @property
    def number_of_remaining_projects(self):
        """See `ITranslationGroup`."""
        total = (
            self.projects.count() +
            self.products.count() +
            self.distributions.count())
        if total > self.TOP_PROJECTS_LIMIT:
            return total - self.TOP_PROJECTS_LIMIT
        else:
            return 0

    def fetchTranslatorData(self):
        """See `ITranslationGroup`."""
        # Fetch Translator, Language, and Person; but also prefetch the
        # icon information.
        using = [
            Translator,
            Language,
            Person,
            LeftJoin(LibraryFileAlias, LibraryFileAlias.id == Person.iconID),
            LeftJoin(
                LibraryFileContent,
                LibraryFileContent.id == LibraryFileAlias.contentID),
            ]
        tables = (
            Translator,
            Language,
            Person,
            LibraryFileAlias,
            LibraryFileContent,
            )
        translator_data = Store.of(self).using(*using).find(
            tables,
            Translator.translationgroup == self,
            Language.id == Translator.languageID,
            Person.id == Translator.translatorID)
        translator_data = translator_data.order_by(Language.englishname)
        mapper = lambda row: row[slice(0, 3)]
        return DecoratedResultSet(translator_data, mapper)

    def fetchProjectsForDisplay(self):
        """See `ITranslationGroup`."""
        # Avoid circular imports.
        from lp.registry.model.product import (
            Product,
            ProductWithLicenses,
            )

        using = [
            Product,
            LeftJoin(LibraryFileAlias, LibraryFileAlias.id == Product.iconID),
            LeftJoin(
                LibraryFileContent,
                LibraryFileContent.id == LibraryFileAlias.contentID),
            ]
        columns = (
            Product,
            ProductWithLicenses.composeLicensesColumn(),
            LibraryFileAlias,
            LibraryFileContent,
            )
        product_data = ISlaveStore(Product).using(*using).find(
            columns,
            Product.translationgroupID == self.id, Product.active == True)
        product_data = product_data.order_by(Product.displayname)

        return [
            ProductWithLicenses(product, tuple(licenses))
            for product, licenses, icon_alias, icon_content in product_data]

    def fetchProjectGroupsForDisplay(self):
        """See `ITranslationGroup`."""
        # Avoid circular imports.
        from lp.registry.model.projectgroup import ProjectGroup

        using = [
            ProjectGroup,
            LeftJoin(
                LibraryFileAlias, LibraryFileAlias.id == ProjectGroup.iconID),
            LeftJoin(
                LibraryFileContent,
                LibraryFileContent.id == LibraryFileAlias.contentID),
            ]
        tables = (
            ProjectGroup,
            LibraryFileAlias,
            LibraryFileContent,
            )
        project_data = ISlaveStore(ProjectGroup).using(*using).find(
            tables,
            ProjectGroup.translationgroupID == self.id,
            ProjectGroup.active == True).order_by(ProjectGroup.displayname)

        return DecoratedResultSet(project_data, operator.itemgetter(0))

    def fetchDistrosForDisplay(self):
        """See `ITranslationGroup`."""
        # Avoid circular imports.
        from lp.registry.model.distribution import Distribution

        using = [
            Distribution,
            LeftJoin(
                LibraryFileAlias, LibraryFileAlias.id == Distribution.iconID),
            LeftJoin(
                LibraryFileContent,
                LibraryFileContent.id == LibraryFileAlias.contentID),
            ]
        tables = (
            Distribution,
            LibraryFileAlias,
            LibraryFileContent,
            )
        distro_data = ISlaveStore(Distribution).using(*using).find(
            tables, Distribution.translationgroupID == self.id).order_by(
            Distribution.displayname)

        return DecoratedResultSet(distro_data, operator.itemgetter(0))


class TranslationGroupSet:

    implements(ITranslationGroupSet)

    title = 'Rosetta Translation Groups'

    def __iter__(self):
        """See `ITranslationGroupSet`."""
        # XXX Danilo 2009-08-25: See bug #418490: we should get
        # group names from their respective celebrities.  For now,
        # just hard-code them so they show up at the top of the
        # listing of all translation groups.
        for group in TranslationGroup.select(
            orderBy=[
                "-(name in ('launchpad-translators', 'ubuntu-translators'))",
                "title"]):
            yield group

    def __getitem__(self, name):
        """See ITranslationGroupSet."""
        return self.getByName(name)

    def getByName(self, name):
        """See ITranslationGroupSet."""
        try:
            return TranslationGroup.byName(name)
        except SQLObjectNotFound:
            raise NotFoundError(name)

    def _get(self):
        return IStore(TranslationGroup).find(TranslationGroup)

    def new(self, name, title, summary, translation_guide_url, owner):
        """See ITranslationGroupSet."""
        return TranslationGroup(
            name=name,
            title=title,
            summary=summary,
            translation_guide_url=translation_guide_url,
            owner=owner)

    def getByPerson(self, person):
        """See `ITranslationGroupSet`."""
        store = Store.of(person)
        origin = [
            TranslationGroup,
            Join(Translator,
                Translator.translationgroupID == TranslationGroup.id),
            Join(TeamParticipation,
                TeamParticipation.teamID == Translator.translatorID),
            ]
        result = store.using(*origin).find(
            TranslationGroup, TeamParticipation.person == person)

        return result.config(distinct=True).order_by(TranslationGroup.title)

    def getGroupsCount(self):
        """See ITranslationGroupSet."""
        return TranslationGroup.select().count()
