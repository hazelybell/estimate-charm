# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Launchpad ProjectGroup-related Database Table Objects."""

__metaclass__ = type
__all__ = [
    'ProjectGroup',
    'ProjectGroupSeries',
    'ProjectGroupSet',
    ]

from sqlobject import (
    AND,
    BoolCol,
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    And,
    In,
    Join,
    SQL,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.answers.enums import QUESTION_STATUS_DEFAULT_SEARCH
from lp.answers.interfaces.faqcollection import IFAQCollection
from lp.answers.interfaces.questioncollection import (
    ISearchableByQuestionOwner,
    )
from lp.answers.model.faq import (
    FAQ,
    FAQSearch,
    )
from lp.answers.model.question import QuestionTargetSearch
from lp.app.enums import ServiceUsage
from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    )
from lp.blueprints.enums import SprintSpecificationStatus
from lp.blueprints.model.specification import (
    HasSpecificationsMixin,
    Specification,
    )
from lp.blueprints.model.specificationsearch import search_specifications
from lp.blueprints.model.sprint import HasSprintsMixin
from lp.bugs.interfaces.bugsummary import IBugSummaryDimension
from lp.bugs.model.bugtarget import (
    BugTargetBase,
    OfficialBugTag,
    )
from lp.bugs.model.structuralsubscription import (
    StructuralSubscriptionTargetMixin,
    )
from lp.code.model.hasbranches import (
    HasBranchesMixin,
    HasMergeProposalsMixin,
    )
from lp.registry.interfaces.person import (
    validate_person_or_closed_team,
    validate_public_person,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import (
    IProjectGroup,
    IProjectGroupSeries,
    IProjectGroupSet,
    )
from lp.registry.model.announcement import MakesAnnouncements
from lp.registry.model.hasdrivers import HasDriversMixin
from lp.registry.model.karma import KarmaContextMixin
from lp.registry.model.milestone import (
    HasMilestonesMixin,
    Milestone,
    ProjectMilestone,
    )
from lp.registry.model.pillar import HasAliasMixin
from lp.registry.model.product import (
    Product,
    ProductSet,
    )
from lp.registry.model.productseries import ProductSeries
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import shortlist
from lp.services.propertycache import cachedproperty
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.worlddata.model.language import Language
from lp.translations.enums import TranslationPermission
from lp.translations.model.potemplate import POTemplate
from lp.translations.model.translationpolicy import TranslationPolicyMixin


class ProjectGroup(SQLBase, BugTargetBase, HasSpecificationsMixin,
                   MakesAnnouncements, HasSprintsMixin, HasAliasMixin,
                   KarmaContextMixin, StructuralSubscriptionTargetMixin,
                   HasBranchesMixin, HasMergeProposalsMixin,
                   HasMilestonesMixin, HasDriversMixin,
                   TranslationPolicyMixin):
    """A ProjectGroup"""

    implements(
        IBugSummaryDimension, IProjectGroup, IFAQCollection, IHasIcon,
        IHasLogo, IHasMugshot, ISearchableByQuestionOwner)

    _table = "Project"

    # db field names
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_person_or_closed_team, notNull=True)
    registrant = ForeignKey(
        dbName='registrant', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    name = StringCol(dbName='name', notNull=True)
    displayname = StringCol(dbName='displayname', notNull=True)
    title = StringCol(dbName='title', notNull=True)
    summary = StringCol(dbName='summary', notNull=True)
    description = StringCol(dbName='description', notNull=True)
    datecreated = UtcDateTimeCol(dbName='datecreated', notNull=True,
        default=UTC_NOW)
    driver = ForeignKey(
        dbName="driver", foreignKey="Person",
        storm_validator=validate_public_person, notNull=False, default=None)
    homepageurl = StringCol(dbName='homepageurl', notNull=False, default=None)
    homepage_content = StringCol(default=None)
    icon = ForeignKey(
        dbName='icon', foreignKey='LibraryFileAlias', default=None)
    logo = ForeignKey(
        dbName='logo', foreignKey='LibraryFileAlias', default=None)
    mugshot = ForeignKey(
        dbName='mugshot', foreignKey='LibraryFileAlias', default=None)
    wikiurl = StringCol(dbName='wikiurl', notNull=False, default=None)
    sourceforgeproject = StringCol(dbName='sourceforgeproject', notNull=False,
        default=None)
    freshmeatproject = StringCol(dbName='freshmeatproject', notNull=False,
        default=None)
    lastdoap = StringCol(dbName='lastdoap', notNull=False, default=None)
    translationgroup = ForeignKey(dbName='translationgroup',
        foreignKey='TranslationGroup', notNull=False, default=None)
    translationpermission = EnumCol(dbName='translationpermission',
        notNull=True, schema=TranslationPermission,
        default=TranslationPermission.OPEN)
    active = BoolCol(dbName='active', notNull=True, default=True)
    reviewed = BoolCol(dbName='reviewed', notNull=True, default=False)
    bugtracker = ForeignKey(
        foreignKey="BugTracker", dbName="bugtracker", notNull=False,
        default=None)
    bug_reporting_guidelines = StringCol(default=None)
    bug_reported_acknowledgement = StringCol(default=None)

    @property
    def pillar_category(self):
        """See `IPillar`."""
        return "Project Group"

    def getProducts(self, user):
        results = Store.of(self).find(
            Product, Product.project == self, Product.active == True,
            ProductSet.getProductPrivacyFilter(user))
        return results.order_by(Product.displayname)

    @cachedproperty
    def products(self):
        return list(self.getProducts(getUtility(ILaunchBag).user))

    def getProduct(self, name):
        return Product.selectOneBy(project=self, name=name)

    def getConfigurableProducts(self):
        return [product for product in self.products
                if check_permission('launchpad.Edit', product)]

    @property
    def drivers(self):
        """See `IHasDrivers`."""
        if self.driver is not None:
            return [self.driver]
        return []

    def getTranslatables(self):
        """Return an iterator over products that are translatable in LP.

        Only products with IProduct.translations_usage set to
        ServiceUsage.LAUNCHPAD are considered translatable.
        """
        store = Store.of(self)
        origin = [
            Product,
            Join(ProductSeries, Product.id == ProductSeries.productID),
            Join(POTemplate, ProductSeries.id == POTemplate.productseriesID),
            ]
        return store.using(*origin).find(
            Product,
            Product.project == self.id,
            Product.translations_usage == ServiceUsage.LAUNCHPAD,
            ).config(distinct=True)

    @cachedproperty
    def translatables(self):
        """See `IProjectGroup`."""
        return list(self.getTranslatables())

    def has_translatable(self):
        """See `IProjectGroup`."""
        return len(self.translatables) > 0

    def sharesTranslationsWithOtherSide(self, person, language,
                                        sourcepackage=None,
                                        purportedly_upstream=False):
        """See `ITranslationPolicy`."""
        assert sourcepackage is None, (
            "Got a SourcePackage for a ProjectGroup!")
        # ProjectGroup translations are considered upstream.  They are
        # automatically shared.
        return True

    def has_branches(self):
        """ See `IProjectGroup`."""
        return not self.getBranches().is_empty()

    def _getBaseQueryAndClauseTablesForQueryingSprints(self):
        query = """
            Product.project = %s
            AND Specification.product = Product.id
            AND Specification.id = SprintSpecification.specification
            AND SprintSpecification.sprint = Sprint.id
            AND SprintSpecification.status = %s
            """ % sqlvalues(self, SprintSpecificationStatus.ACCEPTED)
        return query, ['Product', 'Specification', 'SprintSpecification']

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       series=None, need_people=True, need_branches=True,
                       need_workitems=False):
        """See `IHasSpecifications`."""
        base_clauses = [
            Specification.productID == Product.id,
            Product.projectID == self.id]
        tables = [Specification]
        if series:
            base_clauses.append(ProductSeries.name == series)
            tables.append(
                Join(ProductSeries,
                Specification.productseriesID == ProductSeries.id))
        return search_specifications(
            self, base_clauses, user, sort, quantity, filter, tables=tables,
            need_people=need_people, need_branches=need_branches,
            need_workitems=need_workitems)

    def _customizeSearchParams(self, search_params):
        """Customize `search_params` for this milestone."""
        search_params.setProject(self)

    def _getOfficialTagClause(self):
        """See `OfficialBugTagTargetMixin`."""
        And(ProjectGroup.id == Product.projectID,
            Product.id == OfficialBugTag.productID)

    @property
    def official_bug_tags(self):
        """See `IHasBugs`."""
        store = Store.of(self)
        result = store.find(
            OfficialBugTag.tag,
            OfficialBugTag.product == Product.id,
            Product.project == self.id).order_by(OfficialBugTag.tag)
        result.config(distinct=True)
        return result

    def getBugSummaryContextWhereClause(self):
        """See BugTargetBase."""
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        product_ids = [product.id for product in self.products]
        if not product_ids:
            return False
        return BugSummary.product_id.is_in(product_ids)

    # IQuestionCollection
    def searchQuestions(self, search_text=None,
                        status=QUESTION_STATUS_DEFAULT_SEARCH,
                        language=None, sort=None, owner=None,
                        needs_attention_from=None, unsupported=False):
        """See `IQuestionCollection`."""
        if unsupported:
            unsupported_target = self
        else:
            unsupported_target = None

        return QuestionTargetSearch(
            project=self,
            search_text=search_text, status=status,
            language=language, sort=sort, owner=owner,
            needs_attention_from=needs_attention_from,
            unsupported_target=unsupported_target).getResults()

    def getQuestionLanguages(self):
        """See `IQuestionCollection`."""
        return set(Language.select("""
            Language.id = Question.language AND
            Question.product = Product.id AND
            Product.project = %s""" % sqlvalues(self.id),
            clauseTables=['Question', 'Product'], distinct=True))

    @property
    def bugtargetname(self):
        """See IBugTarget."""
        return self.name

    # IFAQCollection
    def getFAQ(self, id):
        """See `IQuestionCollection`."""
        faq = FAQ.getForTarget(id, None)
        if (faq is not None
            and IProduct.providedBy(faq.target)
            and faq.target in self.products):
            # Filter out faq not related to this project.
            return faq
        else:
            return None

    def searchFAQs(self, search_text=None, owner=None, sort=None):
        """See `IQuestionCollection`."""
        return FAQSearch(
            search_text=search_text, owner=owner, sort=sort,
            project=self).getResults()

    def hasProducts(self):
        """Returns True if a project has products associated with it, False
        otherwise.

        If the project group has < 1 product, selected links will be disabled.
        This is to avoid situations where users try to file bugs against
        empty project groups (Malone bug #106523).
        """
        return len(self.products) != 0

    def _getMilestoneCondition(self):
        """See `HasMilestonesMixin`."""
        user = getUtility(ILaunchBag).user
        privacy_filter = ProductSet.getProductPrivacyFilter(user)
        return And(
            Milestone.productID == Product.id,
            Product.projectID == self.id,
            privacy_filter)

    def _getMilestones(self, user, only_active):
        """Return a list of milestones for this project group.

        If only_active is True, only active milestones are returned,
        else all milestones.

        A project group has a milestone named 'A', if at least one of its
        products has a milestone named 'A'.
        """
        store = Store.of(self)

        columns = (
            Milestone.name,
            SQL('MIN(Milestone.dateexpected)'),
            SQL('BOOL_OR(Milestone.active)'),
            )
        privacy_filter = ProductSet.getProductPrivacyFilter(user)
        conditions = And(Milestone.product == Product.id,
                         Product.project == self,
                         Product.active == True,
                         privacy_filter)
        result = store.find(columns, conditions)
        result.group_by(Milestone.name)
        if only_active:
            result.having('BOOL_OR(Milestone.active) = TRUE')
        # MIN(Milestone.dateexpected) has to be used to match the
        # aggregate function in the `columns` variable.
        result.order_by(
            'milestone_sort_key(MIN(Milestone.dateexpected), Milestone.name) '
            'DESC')
        # An extra query is required here in order to get the correct
        # products without affecting the group/order of the query above.
        products_by_name = {}
        if result.any() is not None:
            milestone_names = [data[0] for data in result]
            product_conditions = And(
                Product.project == self,
                Milestone.product == Product.id,
                Product.active == True,
                privacy_filter,
                In(Milestone.name, milestone_names))
            for product, name in (
                store.find((Product, Milestone.name), product_conditions)):
                if name not in products_by_name.keys():
                    products_by_name[name] = product
        return shortlist(
            [ProjectMilestone(
                self, name, dateexpected, active,
                products_by_name.get(name, None))
             for name, dateexpected, active in result])

    @property
    def has_milestones(self):
        """See `IHasMilestones`."""
        store = Store.of(self)
        result = store.find(
            Milestone.id,
            And(Milestone.product == Product.id,
                Product.project == self,
                Product.active == True))
        return result.any() is not None

    @property
    def milestones(self):
        """See `IProjectGroup`."""
        user = getUtility(ILaunchBag).user
        return self._getMilestones(user, only_active=True)

    @property
    def product_milestones(self):
        """Hack to avoid the ProjectMilestone in MilestoneVocabulary."""
        # XXX: bug=644977 Robert Collins - this is a workaround for
        # inconsistency in project group milestone use.
        return self._get_milestones()

    @property
    def all_milestones(self):
        """See `IProjectGroup`."""
        user = getUtility(ILaunchBag).user
        return self._getMilestones(user, only_active=False)

    def getMilestone(self, name):
        """See `IProjectGroup`."""
        for milestone in self.all_milestones:
            if milestone.name == name:
                return milestone
        return None

    def getSeries(self, series_name):
        """See `IProjectGroup.`"""
        has_series = ProductSeries.selectFirst(
            AND(ProductSeries.q.productID == Product.q.id,
                ProductSeries.q.name == series_name,
                Product.q.projectID == self.id), orderBy='id')

        if has_series is None:
            return None

        return ProjectGroupSeries(self, series_name)

    def _get_usage(self, attr):
        """Determine ProjectGroup usage based on individual projects.

        By default, return ServiceUsage.UNKNOWN.
        If any project uses Launchpad, return ServiceUsage.LAUNCHPAD.
        Otherwise, return the ServiceUsage of the last project that was
        not ServiceUsage.UNKNOWN.
        """
        result = ServiceUsage.UNKNOWN
        for product in self.products:
            product_usage = getattr(product, attr)
            if product_usage != ServiceUsage.UNKNOWN:
                result = product_usage
                if product_usage == ServiceUsage.LAUNCHPAD:
                    break
        return result

    @property
    def answers_usage(self):
        return self._get_usage('answers_usage')

    @property
    def blueprints_usage(self):
        return self._get_usage('blueprints_usage')

    @property
    def translations_usage(self):
        if self.has_translatable():
            return ServiceUsage.LAUNCHPAD
        return ServiceUsage.UNKNOWN

    @property
    def codehosting_usage(self):
        # Project groups do not support submitting code.
        return ServiceUsage.NOT_APPLICABLE

    @property
    def bug_tracking_usage(self):
        return self._get_usage('bug_tracking_usage')

    @property
    def uses_launchpad(self):
        if (self.answers_usage == ServiceUsage.LAUNCHPAD
            or self.blueprints_usage == ServiceUsage.LAUNCHPAD
            or self.translations_usage == ServiceUsage.LAUNCHPAD
            or self.codehosting_usage == ServiceUsage.LAUNCHPAD
            or self.bug_tracking_usage == ServiceUsage.LAUNCHPAD):
            return True
        return False


class ProjectGroupSet:
    implements(IProjectGroupSet)

    def __init__(self):
        self.title = 'Project groups registered in Launchpad'

    def __iter__(self):
        return iter(ProjectGroup.selectBy(active=True))

    def __getitem__(self, name):
        projectgroup = self.getByName(name=name, ignore_inactive=True)
        if projectgroup is None:
            raise NotFoundError(name)
        return projectgroup

    def get(self, projectgroupid):
        """See `lp.registry.interfaces.projectgroup.IProjectGroupSet`.

        >>> getUtility(IProjectGroupSet).get(1).name
        u'apache'
        >>> getUtility(IProjectGroupSet).get(-1)
        Traceback (most recent call last):
        ...
        NotFoundError: -1
        """
        try:
            project = ProjectGroup.get(projectgroupid)
        except SQLObjectNotFound:
            raise NotFoundError(projectgroupid)
        return project

    def getByName(self, name, ignore_inactive=False):
        """See `IProjectGroupSet`."""
        pillar = getUtility(IPillarNameSet).getByName(name, ignore_inactive)
        if not IProjectGroup.providedBy(pillar):
            return None
        return pillar

    def new(self, name, displayname, title, homepageurl, summary,
            description, owner, mugshot=None, logo=None, icon=None,
            registrant=None, bug_supervisor=None, driver=None):
        """See `lp.registry.interfaces.projectgroup.IProjectGroupSet`."""
        if registrant is None:
            registrant = owner
        return ProjectGroup(
            name=name,
            displayname=displayname,
            title=title,
            summary=summary,
            description=description,
            homepageurl=homepageurl,
            owner=owner,
            registrant=registrant,
            datecreated=UTC_NOW,
            mugshot=mugshot,
            logo=logo,
            icon=icon)

    def count_all(self):
        return ProjectGroup.select().count()

    def forReview(self):
        return ProjectGroup.select("reviewed IS FALSE")

    def search(self, text=None, search_products=False, show_inactive=False):
        """Search through the Registry database for project groups that match
        the query terms. text is a piece of text in the title / summary /
        description fields of project group (and possibly product). soyuz,
        bazaar, malone etc are hints as to whether the search
        should be limited to projects that are active in those Launchpad
        applications.
        """
        if text:
            text = text.replace("%", "%%")
        clauseTables = set()
        clauseTables.add('Project')
        queries = []

        if text:
            if search_products:
                clauseTables.add('Product')
                product_query = "Product.fti @@ ftq(%s)" % sqlvalues(text)
                queries.append(product_query)
            else:
                project_query = "Project.fti @@ ftq(%s)" % sqlvalues(text)
                queries.append(project_query)

        if 'Product' in clauseTables:
            queries.append('Product.project=Project.id')

        if not show_inactive:
            queries.append('Project.active IS TRUE')
            if 'Product' in clauseTables:
                queries.append('Product.active IS TRUE')

        query = " AND ".join(queries)
        return ProjectGroup.select(
            query, distinct=True, clauseTables=clauseTables)


class ProjectGroupSeries(HasSpecificationsMixin):
    """See `IProjectGroupSeries`."""

    implements(IProjectGroupSeries)

    def __init__(self, project, name):
        self.project = project
        self.name = name

    def specifications(self, user, sort=None, quantity=None, filter=None,
                       need_people=True, need_branches=True,
                       need_workitems=False):
        return self.project.specifications(
            user, sort, quantity, filter, self.name, need_people=need_people,
            need_branches=need_branches, need_workitems=need_workitems)

    @property
    def title(self):
        return "%s Series %s" % (self.project.title, self.name)

    @property
    def displayname(self):
        return self.name
