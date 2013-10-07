# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Vocabularies for content objects.

Vocabularies that represent a set of content objects should be in this module.
Those vocabularies that are only used for providing a UI are better placed in
the browser code.

Note that you probably shouldn't be importing stuff from these modules, as it
is better to have your schema's fields look up the vocabularies by name. Some
of these vocabularies will only work if looked up by name, as they require
context to calculate the available options. Obtaining a vocabulary by name
also avoids circular import issues.

eg.

class IFoo(Interface):
    thingy = Choice(..., vocabulary='Thingies')

The binding of name -> class is done in the configure.zcml
"""

__metaclass__ = type

__all__ = [
    'ActiveMailingListVocabulary',
    'AdminMergeablePersonVocabulary',
    'AllUserTeamsParticipationVocabulary',
    'AllUserTeamsParticipationPlusSelfVocabulary',
    'CommercialProjectsVocabulary',
    'DistributionOrProductOrProjectGroupVocabulary',
    'DistributionOrProductVocabulary',
    'DistributionVocabulary',
    'DistroSeriesDerivationVocabulary',
    'DistroSeriesDifferencesVocabulary',
    'DistroSeriesVocabulary',
    'FeaturedProjectVocabulary',
    'FilteredDistroSeriesVocabulary',
    'FilteredProductSeriesVocabulary',
    'KarmaCategoryVocabulary',
    'MilestoneVocabulary',
    'NewPillarGranteeVocabulary',
    'NonMergedPeopleAndTeamsVocabulary',
    'person_team_participations_vocabulary_factory',
    'PersonAccountToMergeVocabulary',
    'PersonActiveMembershipVocabulary',
    'ProductReleaseVocabulary',
    'ProductSeriesVocabulary',
    'ProductVocabulary',
    'project_products_vocabulary_factory',
    'ProjectGroupVocabulary',
    'SourcePackageNameVocabulary',
    'UserTeamsParticipationPlusSelfVocabulary',
    'UserTeamsParticipationVocabulary',
    'ValidPersonOrTeamVocabulary',
    'ValidPersonVocabulary',
    'ValidTeamMemberVocabulary',
    'ValidTeamOwnerVocabulary',
    'ValidTeamVocabulary',
    ]


from operator import attrgetter

from sqlobject import (
    AND,
    CONTAINSSTRING,
    OR,
    )
from storm.expr import (
    And,
    Desc,
    Join,
    LeftJoin,
    Or,
    Select,
    SQL,
    Union,
    With,
    )
from storm.info import ClassAlias
from zope.component import getUtility
from zope.interface import implements
from zope.schema.interfaces import IVocabularyTokenized
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )
from zope.security.interfaces import Unauthorized
from zope.security.proxy import (
    isinstance as zisinstance,
    removeSecurityProxy,
    )

from lp.blueprints.interfaces.specification import ISpecification
from lp.code.interfaces.branch import IBranch
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    PersonVisibility,
    )
from lp.registry.interfaces.accesspolicy import IAccessPolicySource
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.distroseriesdifference import (
    IDistroSeriesDifference,
    )
from lp.registry.interfaces.mailinglist import (
    IMailingListSet,
    MailingListStatus,
    )
from lp.registry.interfaces.milestone import (
    IMilestoneSet,
    IProjectGroupMilestone,
    )
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    ITeam,
    )
from lp.registry.interfaces.pillar import (
    IPillar,
    IPillarName,
    )
from lp.registry.interfaces.product import (
    IProduct,
    IProductSet,
    )
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.model.distribution import Distribution
from lp.registry.model.distroseries import DistroSeries
from lp.registry.model.distroseriesdifference import DistroSeriesDifference
from lp.registry.model.distroseriesparent import DistroSeriesParent
from lp.registry.model.featuredproject import FeaturedProject
from lp.registry.model.karma import KarmaCategory
from lp.registry.model.mailinglist import MailingList
from lp.registry.model.milestone import Milestone
from lp.registry.model.person import (
    get_person_visibility_terms,
    IrcID,
    Person,
    )
from lp.registry.model.pillar import PillarName
from lp.registry.model.product import (
    Product,
    ProductSet,
    )
from lp.registry.model.productrelease import ProductRelease
from lp.registry.model.productseries import ProductSeries
from lp.registry.model.projectgroup import ProjectGroup
from lp.registry.model.sourcepackagename import SourcePackageName
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database import bulk
from lp.services.database.decoratedresultset import DecoratedResultSet
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    quote,
    quote_like,
    SQLBase,
    sqlvalues,
    )
from lp.services.helpers import (
    ensure_unicode,
    shortlist,
    )
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressStatus,
    VALID_EMAIL_STATUSES,
    )
from lp.services.identity.model.account import Account
from lp.services.identity.model.emailaddress import EmailAddress
from lp.services.propertycache import (
    cachedproperty,
    get_property_cache,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import nearest
from lp.services.webapp.vocabulary import (
    BatchedCountableIterator,
    CountableIterator,
    FilteredVocabularyBase,
    IHugeVocabulary,
    NamedSQLObjectHugeVocabulary,
    NamedSQLObjectVocabulary,
    SQLObjectVocabularyBase,
    VocabularyFilter,
    )
from lp.soyuz.model.distroarchseries import DistroArchSeries


class BasePersonVocabulary:
    """This is a base class used by all different Person Vocabularies."""

    _table = Person

    def toTerm(self, obj):
        """Return the term for this object."""
        try:
            return SimpleTerm(obj, obj.name, obj.displayname)
        except Unauthorized:
            return None

    def getTermByToken(self, token):
        """Return the term for the given token.

        If the token contains an '@', treat it like an email. Otherwise,
        treat it like a name.
        """
        token = ensure_unicode(token)
        if "@" in token:
            # This looks like an email token, so let's do an object
            # lookup based on that.
            email = IStore(EmailAddress).find(
                EmailAddress,
                EmailAddress.status.is_in(VALID_EMAIL_STATUSES),
                EmailAddress.email.lower() == token.strip().lower()).one()
            if email is None:
                raise LookupError(token)
            return self.toTerm(email.person)
        else:
            # This doesn't look like an email, so let's simply treat
            # it like a name.
            person = getUtility(IPersonSet).getByName(token)
            if person is None:
                raise LookupError(token)
            term = self.toTerm(person)
            if term is None:
                raise LookupError(token)
            return term


class KarmaCategoryVocabulary(NamedSQLObjectVocabulary):
    """All `IKarmaCategory` objects vocabulary."""
    _table = KarmaCategory
    _orderBy = 'name'


class ProductVocabulary(SQLObjectVocabularyBase):
    """All `IProduct` objects vocabulary."""
    implements(IHugeVocabulary)
    step_title = 'Search'

    _table = Product
    _orderBy = 'displayname'
    displayname = 'Select a project'

    def __contains__(self, obj):
        # Sometimes this method is called with an SQLBase instance, but
        # z3 form machinery sends through integer ids. This might be due
        # to a bug somewhere.
        where = "active='t' AND id=%d"
        if zisinstance(obj, SQLBase):
            product = self._table.selectOne(where % obj.id)
            return product is not None and product == obj
        else:
            product = self._table.selectOne(where % int(obj))
            return product is not None

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.name, obj.title)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        # Product names are always lowercase.
        token = token.lower()
        product = self._table.selectOneBy(name=token, active=True)
        if product is None:
            raise LookupError(token)
        return self.toTerm(product)

    def search(self, query, vocab_filter=None):
        """See `SQLObjectVocabularyBase`.

        Returns products where the product name, displayname, title,
        summary, or description contain the given query. Returns an empty list
        if query is None or an empty string.
        """
        if query:
            query = ensure_unicode(query)
            like_query = query.lower()
            like_query = "'%%%%' || %s || '%%%%'" % quote_like(like_query)
            fti_query = quote(query)
            if vocab_filter is None:
                vocab_filter = []
            where_clause = And(
                SQL(
                    "active = 't' AND (name LIKE %s OR fti @@ ftq(%s))" % (
                        like_query, fti_query)),
                ProductSet.getProductPrivacyFilter(
                    getUtility(ILaunchBag).user), *vocab_filter)
            order_by = SQL(
                '(CASE name WHEN %s THEN 1 '
                ' ELSE rank(fti, ftq(%s)) END) DESC, displayname, name'
                % (fti_query, fti_query))
            return IStore(Product).find(self._table, where_clause).order_by(
                order_by).config(limit=100)

        return self.emptySelectResults()


class ProjectGroupVocabulary(SQLObjectVocabularyBase):
    """All `IProjectGroup` objects vocabulary."""
    implements(IHugeVocabulary)

    _table = ProjectGroup
    _orderBy = 'displayname'
    displayname = 'Select a project group'
    step_title = 'Search'

    def __contains__(self, obj):
        where = "active='t' and id=%d"
        if zisinstance(obj, SQLBase):
            project = self._table.selectOne(where % obj.id)
            return project is not None and project == obj
        else:
            project = self._table.selectOne(where % int(obj))
            return project is not None

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.name, obj.title)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        project = self._table.selectOneBy(name=token, active=True)
        if project is None:
            raise LookupError(token)
        return self.toTerm(project)

    def search(self, query, vocab_filter=None):
        """See `SQLObjectVocabularyBase`.

        Returns projects where the project name, displayname, title,
        summary, or description contain the given query. Returns an empty list
        if query is None or an empty string.
        """
        if query:
            query = ensure_unicode(query)
            like_query = query.lower()
            like_query = "'%%' || %s || '%%'" % quote_like(like_query)
            fti_query = quote(query)
            sql = "active = 't' AND (name LIKE %s OR fti @@ ftq(%s))" % (
                    like_query, fti_query)
            return self._table.select(sql)
        return self.emptySelectResults()


def project_products_vocabulary_factory(context):
    """Return a SimpleVocabulary containing the project's products."""
    assert context is not None
    project = IProjectGroup(context)
    return SimpleVocabulary([
        SimpleTerm(product, product.name, title=product.displayname)
        for product in project.products])


class UserTeamsParticipationVocabulary(SQLObjectVocabularyBase):
    """Describes the public teams in which the current user participates."""
    _table = Person
    _orderBy = 'displayname'

    INCLUDE_PRIVATE_TEAM = False

    EXCLUSIVE_TEAMS_ONLY = False

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.name, obj.unique_displayname)

    def __iter__(self):
        kw = {}
        if self._orderBy:
            kw['orderBy'] = self._orderBy
        launchbag = getUtility(ILaunchBag)
        if launchbag.user:
            user = launchbag.user
            for team in user.teams_participated_in:
                if ((team.visibility == PersonVisibility.PUBLIC
                    or self.INCLUDE_PRIVATE_TEAM) and
                    (team.membership_policy in EXCLUSIVE_TEAM_POLICY
                    or not self.EXCLUSIVE_TEAMS_ONLY)):
                    yield self.toTerm(team)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        launchbag = getUtility(ILaunchBag)
        if launchbag.user:
            user = launchbag.user
            for team in user.teams_participated_in:
                if team.name == token:
                    return self.getTerm(team)
        raise LookupError(token)


class NonMergedPeopleAndTeamsVocabulary(
        BasePersonVocabulary, SQLObjectVocabularyBase):
    """The set of all non-merged people and teams.

    If you use this vocabulary you need to make sure that any code which uses
    the people provided by it know how to deal with people which don't have
    a preferred email address, that is, unvalidated person profiles.
    """
    implements(IHugeVocabulary)

    _orderBy = ['displayname']
    displayname = 'Select a Person or Team'
    step_title = 'Search'

    def __contains__(self, obj):
        return obj in self._select()

    def _select(self, text=""):
        """Return `IPerson` objects that match the text."""
        return getUtility(IPersonSet).find(text)

    def search(self, text, vocab_filter=None):
        """See `SQLObjectVocabularyBase`.

        Return people/teams whose fti or email address match :text.
        """
        if not text:
            return self.emptySelectResults()

        return self._select(ensure_unicode(text))


class PersonAccountToMergeVocabulary(
        BasePersonVocabulary, SQLObjectVocabularyBase):
    """The set of all non-merged people with at least one email address.

    This vocabulary is a very specialized one, meant to be used only to choose
    accounts to merge. You *don't* want to use it.
    """
    implements(IHugeVocabulary)

    _orderBy = ['displayname']
    displayname = 'Select a Person to Merge'
    step_title = 'Search'
    must_have_email = True

    def __contains__(self, obj):
        return obj in self._select()

    def _select(self, text=""):
        """Return `IPerson` objects that match the text."""
        return getUtility(IPersonSet).findPerson(
            text, exclude_inactive_accounts=False,
            must_have_email=self.must_have_email)

    def search(self, text, vocab_filter=None):
        """See `SQLObjectVocabularyBase`.

        Return people whose fti or email address match :text.
        """
        if not text:
            return self.emptySelectResults()

        text = ensure_unicode(text)
        return self._select(text)


class AdminMergeablePersonVocabulary(PersonAccountToMergeVocabulary):
    """The set of all non-merged people.

    This vocabulary is a very specialized one, meant to be used only for
    admins to choose accounts to merge. You *don't* want to use it.
    """
    must_have_email = False


class VocabularyFilterPerson(VocabularyFilter):
    # A filter returning just persons.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'PERSON', 'Person',
            'Display search results for people only')

    @property
    def filter_terms(self):
        return [Person.teamownerID == None]


class VocabularyFilterTeam(VocabularyFilter):
    # A filter returning just teams.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'TEAM', 'Team',
            'Display search results for teams only')

    @property
    def filter_terms(self):
        return [Person.teamownerID != None]


class ValidPersonOrTeamVocabulary(
        BasePersonVocabulary, SQLObjectVocabularyBase):
    """The set of valid, viewable Persons/Teams in Launchpad.

    A Person is considered valid if she has a preferred email address, and
    Person.merged is None. Teams have no restrictions at all, which means that
    all teams the user has the permission to view are considered valid.  A
    user can view private teams in which she is a member and any public team.

    This vocabulary is registered as ValidPersonOrTeam, ValidAssignee,
    ValidMaintainer and ValidOwner, because they have exactly the same
    requisites.
    """
    implements(IHugeVocabulary)

    displayname = 'Select a Person or Team'
    step_title = 'Search'
    # This is what subclasses must change if they want any extra filtering of
    # results.
    extra_clause = True
    extra_tables = ()

    # Subclasses should override this property to allow null searches to
    # return all results.  If false, an empty result set is returned.
    allow_null_search = False

    # Cache table to use for checking validity.
    cache_table_name = 'ValidPersonOrTeamCache'

    LIMIT = 100

    PERSON_FILTER = VocabularyFilterPerson()
    TEAM_FILTER = VocabularyFilterTeam()

    def __contains__(self, obj):
        return obj in self._doSearch()

    @cachedproperty
    def store(self):
        """The storm store."""
        return IStore(Product)

    @cachedproperty
    def _karma_context_constraint(self):
        context = nearest(self.context, IPillar)
        if IProduct.providedBy(context):
            karma_context_column = 'product'
        elif IDistribution.providedBy(context):
            karma_context_column = 'distribution'
        elif IProjectGroup.providedBy(context):
            karma_context_column = 'project'
        else:
            return None
        return '%s = %d' % (karma_context_column, context.id)

    def _doSearch(self, text="", vocab_filter=None):
        """Return the people/teams whose fti or email address match :text:"""
        extra_clauses = [self.extra_clause]
        if vocab_filter:
            extra_clauses.extend(vocab_filter.filter_terms)

        # Short circuit if there is no search text - all valid people and/or
        # teams have been requested. We still honour the vocab filter.
        if not text:
            tables = [
                Person,
                Join(self.cache_table_name,
                     SQL("%s.id = Person.id" % self.cache_table_name)),
                ]
            tables.extend(self.extra_tables)
            result = self.store.using(*tables).find(
                Person,
                get_person_visibility_terms(getUtility(ILaunchBag).user),
                Person.merged == None,
                *extra_clauses)
            result.order_by(Person.displayname, Person.name)
        else:
            # Do a full search based on the text given.

            # Create a query that will match persons and teams that
            # have the search text in the fti, at the start of their email
            # address, as their full IRC nickname, or at the start of their
            # displayname.
            # Since we may be eliminating results with the limit to improve
            # performance, we sort by the rank, so that we will always get
            # the best results. The fti rank will be between 0 and 1.
            # Note we use lower() instead of the non-standard ILIKE because
            # ILIKE doesn't hit the indexes.
            # The '%%' is necessary because storm variable substitution
            # converts it to '%'.

            # This is the SQL that will give us the IDs of the people we want
            # in the result.
            matching_person_sql = SQL("""
                SELECT id, MAX(rank) AS rank
                FROM (
                    SELECT Person.id,
                    (case
                        when person.name=lower(?) then 100
                        when person.name like lower(?) || '%%' then 0.6
                        when lower(person.displayname) like lower(?)
                            || '%%' then 0.5
                        else rank(fti, ftq(?))
                    end) as rank
                    FROM Person
                    WHERE Person.name LIKE lower(?) || '%%'
                    or lower(Person.displayname) LIKE lower(?) || '%%'
                    or Person.fti @@ ftq(?)
                    UNION ALL
                    SELECT Person.id, 0.8 AS rank
                    FROM Person, IrcID
                    WHERE Person.id = IrcID.person
                        AND LOWER(IrcID.nickname) = LOWER(?)
                    UNION ALL
                    SELECT Person.id, 0.4 AS rank
                    FROM Person, EmailAddress
                    WHERE Person.id = EmailAddress.person
                        AND LOWER(EmailAddress.email) LIKE lower(?) || '%%'
                        AND status IN (?, ?)
                ) AS person_match
                GROUP BY id
            """, (text, text, text, text, text, text, text, text, text,
                  EmailAddressStatus.VALIDATED.value,
                  EmailAddressStatus.PREFERRED.value))

            # The tables for persons and teams that match the text.
            tables = [
                SQL("MatchingPerson"),
                Person,
                LeftJoin(EmailAddress, EmailAddress.person == Person.id),
                LeftJoin(Account, Account.id == Person.accountID),
                ]
            tables.extend(self.extra_tables)

            # Find all the matching unmerged persons and teams. Persons
            # must additionally have an active account and a preferred
            # email address.
            # We just select the required ids since we will use
            # IPersonSet.getPrecachedPersonsFromIDs to load the results
            matching_with = With("MatchingPerson", matching_person_sql)
            result = self.store.with_(
                matching_with).using(*tables).find(
                Person,
                SQL("Person.id = MatchingPerson.id"),
                Person.merged == None,
                Or(
                    And(
                        Account.status == AccountStatus.ACTIVE,
                        EmailAddress.status ==
                            EmailAddressStatus.PREFERRED),
                    Person.teamowner != None),
                get_person_visibility_terms(getUtility(ILaunchBag).user),
                *extra_clauses)
            # Better ranked matches go first.
            if self._karma_context_constraint:
                rank_order = SQL("""
                    rank * COALESCE(
                        (SELECT LOG(karmavalue) FROM KarmaCache
                         WHERE person = Person.id AND
                            %s
                            AND category IS NULL AND karmavalue > 10),
                        1) DESC""" % self._karma_context_constraint)
            else:
                rank_order = SQL("rank DESC")
            result.order_by(rank_order, Person.displayname, Person.name)
        result.config(limit=self.LIMIT)

        # We will be displaying the person's irc nick(s) and emails in the
        # description so we need to bulk load them for performance, otherwise
        # we get one query per person per attribute.
        def pre_iter_hook(persons):
            emails = bulk.load_referencing(EmailAddress, persons, ['personID'])
            email_by_person = dict(
                (email.personID, email) for email in emails
                if email.status == EmailAddressStatus.PREFERRED)

            for person in persons:
                cache = get_property_cache(person)
                cache.preferredemail = email_by_person.get(person.id, None)
                cache.ircnicknames = []

            for nick in bulk.load_referencing(IrcID, persons, ['personID']):
                get_property_cache(nick.person).ircnicknames.append(nick)

        return DecoratedResultSet(result, pre_iter_hook=pre_iter_hook)

    def search(self, text, vocab_filter=None):
        """Return people/teams whose fti or email address match :text:."""
        if not text:
            if self.allow_null_search:
                text = ''
            else:
                return self.emptySelectResults()

        text = ensure_unicode(text)
        return self._doSearch(text=text, vocab_filter=vocab_filter)

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.search(query, vocab_filter)
        return CountableIterator(results.count(), results, self.toTerm)

    def supportedFilters(self):
        """See `IHugeVocabulary`."""
        return [self.ALL_FILTER, self.PERSON_FILTER, self.TEAM_FILTER]


class ValidTeamVocabulary(ValidPersonOrTeamVocabulary):
    """The set of all valid, public teams in Launchpad."""

    displayname = 'Select a Team'

    # Because the base class does almost everything we need, we just need to
    # restrict the search results to those Persons who have a non-NULL
    # teamowner, i.e. a valid team.
    extra_clause = Person.teamowner != None
    # Search with empty string returns all teams.
    allow_null_search = True

    def supportedFilters(self):
        return []


class ValidPersonVocabulary(ValidPersonOrTeamVocabulary):
    """The set of all valid persons who are not teams in Launchpad."""
    displayname = 'Select a Person'
    # The extra_clause for a valid person is that it not be a team, so
    # teamowner IS NULL.
    extra_clause = Person.teamowner == None
    # Search with empty string returns all valid people.
    allow_null_search = True
    # Cache table to use for checking validity.
    cache_table_name = 'ValidPersonCache'

    def supportedFilters(self):
        return []


class TeamVocabularyMixin:
    """Common methods for team vocabularies."""

    displayname = 'Select a Team or Person'

    @property
    def is_closed_team(self):
        return self.team.membership_policy in EXCLUSIVE_TEAM_POLICY

    @property
    def step_title(self):
        """See `IHugeVocabulary`."""
        if self.is_closed_team:
            return (
                'Search for a restricted team, a moderated team, or a person')
        else:
            return 'Search'


class ValidPersonOrExclusiveTeamVocabulary(TeamVocabularyMixin,
                                ValidPersonOrTeamVocabulary):
    """The set of people and exclusive teams in Launchpad.

    A exclusive team is one for which the membership policy is either
    RESTRICTED or MODERATED.
    """

    @property
    def is_closed_team(self):
        return True

    @property
    def extra_clause(self):
        return Person.membership_policy.is_in(EXCLUSIVE_TEAM_POLICY)


class ValidTeamMemberVocabulary(TeamVocabularyMixin,
                                ValidPersonOrTeamVocabulary):
    """The set of valid members of a given team.

    With the exception of all teams that have this team as a member and the
    team itself, all valid persons and teams are valid members. Restricted
    and moderated teams cannot have open teams as members.
    """

    def __init__(self, context):
        if not context:
            raise AssertionError('ValidTeamMemberVocabulary needs a context.')
        if ITeam.providedBy(context):
            self.team = context
        else:
            raise AssertionError(
                "ValidTeamMemberVocabulary's context must implement ITeam."
                "Got %s" % str(context))

        ValidPersonOrTeamVocabulary.__init__(self, context)

    @property
    def extra_clause(self):
        clause = SQL("""
            Person.id NOT IN (
                SELECT team FROM TeamParticipation
                WHERE person = %d
                )
            """ % self.team.id)
        if self.is_closed_team:
            clause = And(
                clause,
                Person.membership_policy.is_in(EXCLUSIVE_TEAM_POLICY))
        return clause


class ValidTeamOwnerVocabulary(TeamVocabularyMixin,
                               ValidPersonOrTeamVocabulary):
    """The set of Persons/Teams that can be owner of a team.

    With the exception of the team itself and all teams owned by that team,
    all valid persons and teams are valid owners for the team. Restricted
    and moderated teams cannot have open teams as members.
    """

    def __init__(self, context):
        if not context:
            raise AssertionError('ValidTeamOwnerVocabulary needs a context.')

        if IPerson.providedBy(context):
            self.team = context
        elif IPersonSet.providedBy(context):
            # The context is an IPersonSet, which means we're creating a new
            # team and thus we don't need any extra_clause --any valid person
            # or team can be the owner of a newly created team.
            pass
        else:
            raise AssertionError(
                "ValidTeamOwnerVocabulary's context must provide IPerson "
                "or IPersonSet.")
        ValidPersonOrTeamVocabulary.__init__(self, context)

    @property
    def extra_clause(self):
        clause = SQL("""
            (person.teamowner != %d OR person.teamowner IS NULL) AND
            person.id != %d""" % (self.team.id, self.team.id))
        if self.is_closed_team:
            clause = And(
                clause,
                Person.membership_policy.is_in(EXCLUSIVE_TEAM_POLICY))
        return clause


class AllUserTeamsParticipationVocabulary(ValidTeamVocabulary):
    """The set of teams where the current user is a member.

    Other than UserTeamsParticipationVocabulary, this vocabulary includes
    private teams.
    """

    displayname = 'Select a Team of which you are a member'

    def __init__(self, context):
        super(AllUserTeamsParticipationVocabulary, self).__init__(context)
        user = getUtility(ILaunchBag).user
        if user is None:
            self.extra_clause = False
        else:
            # TeamParticipation might already be used for private team
            # access checks, so alias and join it separately here.
            tp_alias = ClassAlias(TeamParticipation)
            self.extra_tables = [
                Join(
                    tp_alias,
                    And(tp_alias.teamID == Person.id,
                        tp_alias.personID == user.id))]


class PersonActiveMembershipVocabulary:
    """All the teams the person is an active member of."""

    implements(IVocabularyTokenized)

    def __init__(self, context):
        assert IPerson.providedBy(context)
        self.context = context

    def _get_teams(self):
        """The teams that the vocabulary is built from."""
        return [membership.team for membership
                in self.context.team_memberships
                if membership.team.visibility == PersonVisibility.PUBLIC]

    def __len__(self):
        """See `IVocabularyTokenized`."""
        return len(self._get_teams())

    def __iter__(self):
        """See `IVocabularyTokenized`."""
        return iter([self.getTerm(team) for team in self._get_teams()])

    def getTerm(self, team):
        """See `IVocabularyTokenized`."""
        if team not in self:
            raise LookupError(team)
        return SimpleTerm(team, team.name, team.displayname)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        for team in self._get_teams():
            if team.name == token:
                return self.getTerm(team)
        else:
            raise LookupError(token)

    def __contains__(self, obj):
        """See `IVocabularyTokenized`."""
        return obj in self._get_teams()


class NewPillarGranteeVocabulary(ValidPersonOrExclusiveTeamVocabulary):
    """The set of people and teams with whom to share information.

    A person or team is eligible for sharing with if they are not already an
    existing grantee for the pillar.
    """

    displayname = 'Share project information'
    step_title = 'Search for user or exclusive team with whom to share'

    def __init__(self, context):
        assert IPillar.providedBy(context)
        super(NewPillarGranteeVocabulary, self).__init__(context)
        aps = getUtility(IAccessPolicySource)
        access_policies = aps.findByPillar([self.context])
        self.policy_ids = [policy.id for policy in access_policies]

    @property
    def extra_clause(self):
        clause = SQL("""
            Person.id NOT IN (
                SELECT grantee FROM AccessPolicyGrantFlat
                WHERE policy in %s
                )
            """ % sqlvalues(self.policy_ids))
        return And(
            clause,
            super(NewPillarGranteeVocabulary, self).extra_clause)


class ActiveMailingListVocabulary(FilteredVocabularyBase):
    """The set of all active mailing lists."""

    implements(IHugeVocabulary)

    displayname = 'Select an active mailing list.'
    step_title = 'Search'

    def __init__(self, context):
        assert context is None, (
            'Unexpected context for ActiveMailingListVocabulary')

    def __iter__(self):
        """See `IIterableVocabulary`."""
        return iter(getUtility(IMailingListSet).active_lists)

    def __len__(self):
        """See `IIterableVocabulary`."""
        return getUtility(IMailingListSet).active_lists.count()

    def __contains__(self, team_list):
        """See `ISource`."""
        # Unlike other __contains__() implementations in this module, and
        # somewhat contrary to the interface definition, this method does not
        # return False when team_list is not an IMailingList.  No interface
        # check of the argument is done here.  Doing the interface check and
        # returning False when we get an unexpected type would be more
        # Pythonic, but we deliberately break that rule because it is
        # considered more helpful to generate an OOPS when the wrong type of
        # object is used in a containment test.  The __contains__() methods in
        # this module that type check their arguments is considered incorrect.
        # This also implies that .getTerm(), contrary to its interface
        # definition, will not always raise LookupError when the term isn't in
        # the vocabulary, because an exceptions from the containment test it
        # does will just be passed on up the call stack.
        return team_list.status == MailingListStatus.ACTIVE

    def toTerm(self, team_list):
        """See `IVocabulary`.

        Turn the team mailing list into a SimpleTerm.
        """
        return SimpleTerm(team_list, team_list.team.name,
                          team_list.team.displayname)

    def getTerm(self, team_list):
        """See `IBaseVocabulary`."""
        if team_list not in self:
            raise LookupError(team_list)
        return self.toTerm(team_list)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        # token should be the team name as a string.
        team_list = getUtility(IMailingListSet).get(token)
        if team_list is None:
            raise LookupError(token)
        return self.getTerm(team_list)

    def search(self, text=None, vocab_filter=None):
        """Search for active mailing lists.

        :param text: The name of a mailing list, which can be a partial
            name.  This actually matches against the name of the team to which
            the mailing list is linked.  If None (the default), all active
            mailing lists are returned.
        :return: An iterator over the active mailing lists matching the query.
        """
        if text is None:
            return getUtility(IMailingListSet).active_lists
        # The mailing list name, such as it has one, is really the name of the
        # team to which it is linked.
        return MailingList.select("""
            MailingList.team = Person.id
            AND Person.fti @@ ftq(%s)
            AND Person.teamowner IS NOT NULL
            AND MailingList.status = %s
            """ % sqlvalues(text, MailingListStatus.ACTIVE),
            clauseTables=['Person'])

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.search(query)
        return CountableIterator(results.count(), results, self.toTerm)


def person_term(person):
    """Return a SimpleTerm for the `Person`."""
    return SimpleTerm(person, person.name, title=person.displayname)


def person_team_participations_vocabulary_factory(context):
    """Return a SimpleVocabulary containing the teams a person
    participate in.
    """
    assert context is not None
    person = IPerson(context)
    return SimpleVocabulary([
        person_term(team) for team in person.teams_participated_in])


class UserTeamsParticipationPlusSelfVocabulary(
    UserTeamsParticipationVocabulary):
    """A vocabulary containing the public teams that the logged
    in user participates in, along with the logged in user themselves.
    """

    def __iter__(self):
        logged_in_user = getUtility(ILaunchBag).user
        yield self.toTerm(logged_in_user)
        super_class = super(UserTeamsParticipationPlusSelfVocabulary, self)
        for person in super_class.__iter__():
            yield person

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        logged_in_user = getUtility(ILaunchBag).user
        if logged_in_user.name == token:
            return self.getTerm(logged_in_user)
        super_class = super(UserTeamsParticipationPlusSelfVocabulary, self)
        return super_class.getTermByToken(token)


class AllUserTeamsParticipationPlusSelfVocabulary(
    UserTeamsParticipationPlusSelfVocabulary):
    """All public and private teams participates in and himself.

    This redefines UserTeamsParticipationVocabulary to include private teams
    and it includes the logged in user from
    UserTeamsParticipationPlusSelfVocabulary.
    """

    INCLUDE_PRIVATE_TEAM = True

    def __init__(self, context=None):
        super_class = super(AllUserTeamsParticipationPlusSelfVocabulary, self)
        super_class.__init__(context)
        if IBranch.providedBy(context):
            self.EXCLUSIVE_TEAMS_ONLY = (
                len(list(context.associatedProductSeries())) > 0)


class UserTeamsParticipationPlusSelfSimpleDisplayVocabulary(
    UserTeamsParticipationPlusSelfVocabulary):
    """Like UserTeamsParticipationPlusSelfVocabulary but the term title is
    the person.displayname rather than unique_displayname.

    This vocab is used for pickers which append the Launchpad id to the
    displayname. If we use the original UserTeamsParticipationPlusSelf vocab,
    the Launchpad id is displayed twice.
    """

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.name, obj.displayname)


class ProductReleaseVocabulary(SQLObjectVocabularyBase):
    """All `IProductRelease` objects vocabulary."""
    implements(IHugeVocabulary)

    displayname = 'Select a Product Release'
    step_title = 'Search'
    _table = ProductRelease
    # XXX carlos Perello Marin 2005-05-16 bugs=687:
    # Sorting by version won't give the expected results, because it's just a
    # text field.  e.g. ["1.0", "2.0", "11.0"] would be sorted as ["1.0",
    # "11.0", "2.0"].
    _orderBy = [Product.q.name, ProductSeries.q.name, Milestone.q.name]
    _clauseTables = ['Product', 'ProductSeries']

    def toTerm(self, obj):
        """See `IVocabulary`."""
        productrelease = obj
        productseries = productrelease.milestone.productseries
        product = productseries.product

        # NB: We use '/' as the separator because '-' is valid in
        # a product.name or productseries.name
        token = '%s/%s/%s' % (
                    product.name, productseries.name, productrelease.version)
        return SimpleTerm(
            obj.id, token, '%s %s %s' % (
                product.name, productseries.name, productrelease.version))

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            productname, productseriesname, dummy = token.split('/', 2)
        except ValueError:
            raise LookupError(token)

        obj = ProductRelease.selectOne(
            AND(ProductRelease.q.milestoneID == Milestone.q.id,
                Milestone.q.productseriesID == ProductSeries.q.id,
                ProductSeries.q.productID == Product.q.id,
                Product.q.name == productname,
                ProductSeries.q.name == productseriesname))
        try:
            return self.toTerm(obj)
        except IndexError:
            raise LookupError(token)

    def search(self, query, vocab_filter=None):
        """Return terms where query is a substring of the version or name"""
        if not query:
            return self.emptySelectResults()

        query = ensure_unicode(query).lower()
        objs = self._table.select(
            AND(
                Milestone.q.id == ProductRelease.q.milestoneID,
                ProductSeries.q.id == Milestone.q.productseriesID,
                Product.q.id == ProductSeries.q.productID,
                OR(
                    CONTAINSSTRING(Product.q.name, query),
                    CONTAINSSTRING(ProductSeries.q.name, query),
                    )
                ),
            orderBy=self._orderBy
            )

        return objs


class ProductSeriesVocabulary(SQLObjectVocabularyBase):
    """All `IProductSeries` objects vocabulary."""
    implements(IHugeVocabulary)

    displayname = 'Select a Release Series'
    step_title = 'Search'
    _table = ProductSeries
    _order_by = [Product.name, ProductSeries.name]
    _clauseTables = ['Product']

    def toTerm(self, obj):
        """See `IVocabulary`."""
        # NB: We use '/' as the separator because '-' is valid in
        # a product.name or productseries.name
        token = '%s/%s' % (obj.product.name, obj.name)
        return SimpleTerm(
            obj, token, '%s %s' % (obj.product.name, obj.name))

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            productname, productseriesname = token.split('/', 1)
        except ValueError:
            raise LookupError(token)

        result = IStore(self._table).find(
            self._table,
            ProductSeries.product == Product.id,
            Product.name == productname,
            ProductSeries.name == productseriesname).one()
        if result is not None:
            return self.toTerm(result)
        raise LookupError(token)

    def search(self, query, vocab_filter=None):
        """Return terms where query is a substring of the name."""
        if not query:
            return self.emptySelectResults()
        user = getUtility(ILaunchBag).user
        privacy_filter = ProductSet.getProductPrivacyFilter(user)
        query = ensure_unicode(query).lower().strip('/')
        # If there is a slash splitting the product and productseries
        # names, they must both match. If there is no slash, we don't
        # know whether it is matching the product or the productseries
        # so we search both for the same string.
        if '/' in query:
            product_query, series_query = query.split('/', 1)
            substring_search = And(
                CONTAINSSTRING(Product.name, product_query),
                CONTAINSSTRING(ProductSeries.name, series_query))
        else:
            substring_search = Or(
                CONTAINSSTRING(Product.name, query),
                CONTAINSSTRING(ProductSeries.name, query))
        result = IStore(self._table).find(
            self._table,
            Product.id == ProductSeries.productID,
            substring_search,
            privacy_filter)
        result = result.order_by(self._order_by)
        return result


class FilteredDistroSeriesVocabulary(SQLObjectVocabularyBase):
    """Describes the series of a particular distribution."""
    _table = DistroSeries
    _orderBy = 'version'

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(
            obj, obj.id, '%s %s' % (obj.distribution.name, obj.name))

    def __iter__(self):
        kw = {}
        if self._orderBy:
            kw['orderBy'] = self._orderBy
        launchbag = getUtility(ILaunchBag)
        if launchbag.distribution:
            distribution = launchbag.distribution
            series = self._table.selectBy(
                distributionID=distribution.id, **kw)
            for series in sorted(series, key=attrgetter('sortkey')):
                yield self.toTerm(series)


class FilteredProductSeriesVocabulary(SQLObjectVocabularyBase):
    """Describes ProductSeries of a particular product."""
    _table = ProductSeries
    _orderBy = ['product', 'name']

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(
            obj, obj.id, '%s %s' % (obj.product.name, obj.name))

    def __iter__(self):
        launchbag = getUtility(ILaunchBag)
        if launchbag.product is not None:
            for series in launchbag.product.series:
                yield self.toTerm(series)


class MilestoneVocabulary(SQLObjectVocabularyBase):
    """The milestones for a target."""
    _table = Milestone
    _orderBy = None

    def toTerm(self, obj):
        """See `IVocabulary`."""
        return SimpleTerm(obj, obj.id, obj.displayname)

    @staticmethod
    def getMilestoneTarget(milestone_context):
        """Return the milestone target."""
        if IDistributionSourcePackage.providedBy(milestone_context):
            target = milestone_context.distribution
        elif ISourcePackage.providedBy(milestone_context):
            target = milestone_context.distroseries
        elif ISpecification.providedBy(milestone_context):
            target = milestone_context.target
        elif IProductSeries.providedBy(milestone_context):
            # Show all the milestones of the product for a product series.
            target = milestone_context.product
        elif (IProjectGroup.providedBy(milestone_context) or
              IProduct.providedBy(milestone_context) or
              IDistribution.providedBy(milestone_context) or
              IDistroSeries.providedBy(milestone_context)):
            target = milestone_context
        else:
            # We didn't find a context that can have milestones attached
            # to it.
            target = None
        return target

    @cachedproperty
    def visible_milestones(self):
        """Return the active milestones."""
        milestone_context = self.context
        target = MilestoneVocabulary.getMilestoneTarget(milestone_context)

        # XXX: Brad Bollenbach 2006-02-24: Listifying milestones is
        # evil, but we need to sort the milestones by a non-database
        # value, for the user to find the milestone they're looking
        # for (particularly when showing *all* milestones on the
        # person pages.)
        #
        # This fixes an urgent bug though, so I think this problem
        # should be revisited after we've unblocked users.
        if target is not None:
            if IProjectGroup.providedBy(target):
                milestones_source = target.product_milestones
            else:
                milestones_source = target.milestones
            milestones = shortlist(milestones_source, longest_expected=40)
        else:
            # We can't use context to reasonably filter the
            # milestones, so let's either just grab all of them,
            # or let's return an empty vocabulary.
            # Generally, returning all milestones is a bad idea: We
            # have at present (2009-04-08) nearly 2000 active milestones,
            # and nobody really wants to search through such a huge list
            # on a web page. This problem is fixed for an IPerson
            # context by browser.person.RelevantMilestonesMixin.
            # getMilestoneWidgetValues() which creates a "sane" milestone
            # set. We need to create the big vocabulary of all visible
            # milestones nevertheless, in order to allow the validation
            # of submitted milestone values.
            #
            # For other targets, like MaloneApplication, we return an empty
            # vocabulary.
            if IPerson.providedBy(self.context):
                milestones = shortlist(
                    getUtility(IMilestoneSet).getVisibleMilestones(),
                    longest_expected=40)
            else:
                milestones = []

        # Prefetch products and distributions for rendering
        # milestones: optimization to reduce the number of queries.
        product_ids = set(
            removeSecurityProxy(milestone).productID
            for milestone in milestones)
        product_ids.discard(None)
        distro_ids = set(
            removeSecurityProxy(milestone).distributionID
            for milestone in milestones)
        distro_ids.discard(None)
        if len(product_ids) > 0:
            list(Product.select("id IN %s" % sqlvalues(product_ids)))
        if len(distro_ids) > 0:
            list(Distribution.select("id IN %s" % sqlvalues(distro_ids)))

        return sorted(milestones, key=attrgetter('displayname'))

    def __iter__(self):
        for milestone in self.visible_milestones:
            yield self.toTerm(milestone)

    def __len__(self):
        return len(self.visible_milestones)

    def __contains__(self, obj):
        if IProjectGroupMilestone.providedBy(obj):
            # ProjectGroup milestones are pseudo content objects
            # which aren't really a part of this vocabulary,
            # but sometimes we want to pass them to fields
            # that rely on this vocabulary for validation
            # so we special-case them here just for that purpose.
            return obj.target.getMilestone(obj.name)
        else:
            return SQLObjectVocabularyBase.__contains__(self, obj)


class CommercialProjectsVocabulary(NamedSQLObjectVocabulary):
    """List all commercial projects.

    A commercial project is an active project that can have a commercial
    subscription to grant access to proprietary features. The vocabulary
    contains the active projects the user maintains, or all active project
    if the user is a registry expert.
    """

    implements(IHugeVocabulary)

    _table = Product
    _orderBy = 'displayname'
    step_title = 'Search'

    @property
    def displayname(self):
        """The vocabulary's display nane."""
        return 'Select a commercial project'

    @cachedproperty
    def product_set(self):
        return getUtility(IProductSet)

    @cachedproperty
    def is_commercial_admin(self):
        """Is the user a commercial admin?"""
        return check_permission('launchpad.Commercial', self.product_set)

    def _doSearch(self, query=None):
        """Return terms where query is in the text of name
        or displayname, or matches the full text index.
        """
        user = self.context
        if user is None:
            return self.emptySelectResults()
        if self.is_commercial_admin:
            projects = self.product_set.search(user, query)
        else:
            projects = user.getOwnedProjects(match_name=query)
        return projects

    def toTerm(self, project):
        """Return the term for this object."""
        return SimpleTerm(project, project.name, project.displayname)

    def getTermByToken(self, token):
        """Return the term for the given token."""
        if self.is_commercial_admin:
            project = self.product_set.getByName(token)
            if project is not None and project.active:
                return self.toTerm(project)
        else:
            search_results = self._doSearch(token)
            for search_result in search_results:
                if search_result.name == token:
                    return self.toTerm(search_result)
        raise LookupError(token)

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `SQLObjectVocabularyBase`."""
        results = self._doSearch(query)
        num = results.count()
        return CountableIterator(num, results, self.toTerm)

    def __iter__(self):
        """See `IVocabulary`."""
        for proj in self._doSearch():
            yield self.toTerm(proj)

    def __contains__(self, project):
        """See `IVocabulary`."""
        if not project.active:
            return False
        if self.is_commercial_admin:
            return True
        return self.context.inTeam(project.owner)


class DistributionVocabulary(NamedSQLObjectVocabulary):
    """All `IDistribution` objects vocabulary."""
    _table = Distribution
    _orderBy = 'name'

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        obj = Distribution.selectOne("name=%s" % sqlvalues(token))
        if obj is None:
            raise LookupError(token)
        else:
            return self.toTerm(obj)

    def search(self, query, vocab_filter=None):
        """Return terms where query is a substring of the name"""
        if not query:
            return self.emptySelectResults()

        query = query.lower()
        like_query = "'%%' || %s || '%%'" % quote_like(query)
        kw = {}
        if self._orderBy:
            kw['orderBy'] = self._orderBy
        return self._table.select("name LIKE %s" % like_query, **kw)


class DistroSeriesVocabulary(NamedSQLObjectVocabulary):
    """All `IDistroSeries` objects vocabulary."""
    _table = DistroSeries
    _orderBy = ["Distribution.displayname", "-DistroSeries.date_created"]
    _clauseTables = ['Distribution']

    def __iter__(self):
        series = self._table.select(
            DistroSeries.q.distributionID == Distribution.q.id,
            orderBy=self._orderBy, clauseTables=self._clauseTables)
        for series in sorted(series, key=attrgetter('sortkey')):
            yield self.toTerm(series)

    @staticmethod
    def toTerm(obj):
        """See `IVocabulary`."""
        # NB: We use '/' as the separator because '-' is valid in
        # a distribution.name
        token = '%s/%s' % (obj.distribution.name, obj.name)
        title = "%s: %s" % (obj.distribution.displayname, obj.title)
        return SimpleTerm(obj, token, title)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        try:
            distroname, distroseriesname = token.split('/', 1)
        except ValueError:
            raise LookupError(token)

        obj = DistroSeries.selectOne('''
                    Distribution.id = DistroSeries.distribution AND
                    Distribution.name = %s AND
                    DistroSeries.name = %s
                    ''' % sqlvalues(distroname, distroseriesname),
                    clauseTables=['Distribution'])
        if obj is None:
            raise LookupError(token)
        else:
            return self.toTerm(obj)

    def search(self, query, vocab_filter=None):
        """Return terms where query is a substring of the name."""
        if not query:
            return self.emptySelectResults()

        query = ensure_unicode(query).lower()
        objs = self._table.select(
                AND(
                    Distribution.q.id == DistroSeries.q.distributionID,
                    OR(
                        CONTAINSSTRING(Distribution.q.name, query),
                        CONTAINSSTRING(DistroSeries.q.name, query))),
                    orderBy=self._orderBy)
        return objs


class DistroSeriesDerivationVocabulary(FilteredVocabularyBase):
    """A vocabulary source for series to derive from.

    Once a distribution has a series that has derived from a series in another
    distribution, all other derived series must also derive from a series in
    the same distribution.

    A distribution can have non-derived series. Any of these can be changed to
    derived at a later date, but as soon as this happens, the above rule
    applies.

    Also, a series must have architectures setup in LP to be a potential
    parent.

    It is permissible for a distribution to have both derived and non-derived
    series at the same time.
    """

    implements(IHugeVocabulary)

    displayname = "Add a parent series"
    step_title = 'Search'

    def __init__(self, context):
        """Create a new vocabulary for the context.

        :param context: It should adaptable to `IDistroSeries`.
        """
        assert IDistroSeries.providedBy(context)
        self.distribution = context.distribution

    def __len__(self):
        """See `IIterableVocabulary`."""
        return self.searchParents().count()

    def __iter__(self):
        """See `IIterableVocabulary`."""
        for series in self.searchParents():
            yield self.toTerm(series)

    def __contains__(self, value):
        """See `IVocabulary`."""
        if not IDistroSeries.providedBy(value):
            return False
        return value.id in [parent.id for parent in self.searchParents()]

    def getTerm(self, value):
        """See `IVocabulary`."""
        if value not in self:
            raise LookupError(value)
        return self.toTerm(value)

    def terms_by_token(self):
        """Mapping of terms by token."""
        return dict((term.token, term) for term in self.terms)

    def getTermByToken(self, token):
        try:
            return self.terms_by_token[token]
        except KeyError:
            raise LookupError(token)

    def toTerm(self, series):
        """Return the term for a parent series."""
        title = "%s: %s" % (series.distribution.displayname, series.title)
        return SimpleTerm(series, series.id, title)

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.searchParents(query)
        return CountableIterator(len(results), results, self.toTerm)

    @cachedproperty
    def terms(self):
        return self.searchParents()

    def find_terms(self, *where):
        """Return a `tuple` of terms matching the given criteria.

        The terms are returned in order. The `Distribution`s related to those
        terms are preloaded at the same time.
        """
        query = IStore(DistroSeries).find(
            (DistroSeries, Distribution),
            DistroSeries.distribution == Distribution.id,
            *where)
        query = query.order_by(
            Distribution.displayname,
            Desc(DistroSeries.date_created)).config(distinct=True)
        return [series for (series, distribution) in query]

    def searchParents(self, query=None):
        """See `IHugeVocabulary`."""
        parent = ClassAlias(DistroSeries, "parent")
        child = ClassAlias(DistroSeries, "child")
        where = []
        if query is not None:
            term = '%' + query.lower() + '%'
            search = Or(
                    DistroSeries.title.lower().like(term),
                    DistroSeries.description.lower().like(term),
                    DistroSeries.summary.lower().like(term))
            where.append(search)
        parent_distributions = list(IStore(DistroSeries).find(
            parent.distributionID, And(
                parent.distributionID != self.distribution.id,
                child.distributionID == self.distribution.id,
                child.id == DistroSeriesParent.derived_series_id,
                parent.id == DistroSeriesParent.parent_series_id)))
        if parent_distributions != []:
            where.append(
                DistroSeries.distributionID.is_in(parent_distributions))
            return self.find_terms(where)
        else:
            # Select only the series with architectures setup in LP.
            where.append(
                DistroSeries.id == DistroArchSeries.distroseriesID)
            where.append(
                DistroSeries.distribution != self.distribution)
            return self.find_terms(where)


class DistroSeriesDifferencesVocabulary(FilteredVocabularyBase):
    """A vocabulary source for differences relating to a series.

    Specifically, all `DistroSeriesDifference`s relating to a derived series.
    """

    implements(IHugeVocabulary)

    displayname = "Choose a difference"
    step_title = 'Search'

    def __init__(self, context):
        """Create a new vocabulary for the context.

        :type context: `IDistroSeries`.
        """
        assert IDistroSeries.providedBy(context)
        self.distroseries = context

    def __len__(self):
        """See `IIterableVocabulary`."""
        return self.searchForDifferences().count()

    def __iter__(self):
        """See `IIterableVocabulary`."""
        for difference in self.searchForDifferences():
            yield self.toTerm(difference)

    def __contains__(self, value):
        """See `IVocabulary`."""
        return (
            IDistroSeriesDifference.providedBy(value) and
            value.derived_series == self.distroseries)

    def getTerm(self, value):
        """See `IVocabulary`."""
        if value not in self:
            raise LookupError(value)
        return self.toTerm(value)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        if not token.isdigit():
            raise LookupError(token)
        difference = IStore(DistroSeriesDifference).get(
            DistroSeriesDifference, int(token))
        if difference is None:
            raise LookupError(token)
        elif difference.derived_series != self.distroseries:
            raise LookupError(token)
        else:
            return self.toTerm(difference)

    @staticmethod
    def toTerm(dsd):
        """Return the term for a `DistroSeriesDifference`."""
        return SimpleTerm(dsd, dsd.id)

    def searchForTerms(self, query=None, vocab_filter=None):
        """See `IHugeVocabulary`."""
        results = self.searchForDifferences()
        return CountableIterator(results.count(), results, self.toTerm)

    def searchForDifferences(self):
        """The set of `DistroSeriesDifference`s related to the context.

        :return: `IResultSet` yielding `IDistroSeriesDifference`.
        """
        return DistroSeriesDifference.getForDistroSeries(self.distroseries)


class VocabularyFilterProject(VocabularyFilter):
    # A filter returning just projects.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'PROJECT', 'Project',
            'Display search results associated with projects')

    @property
    def filter_terms(self):
        return [PillarName.product != None]


class VocabularyFilterProjectGroup(VocabularyFilter):
    # A filter returning just project groups.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'PROJECTGROUP', 'Project Group',
            'Display search results associated with project groups')

    @property
    def filter_terms(self):
        return [PillarName.project != None]


class VocabularyFilterDistribution(VocabularyFilter):
    # A filter returning just distros.

    def __new__(cls):
        return super(VocabularyFilter, cls).__new__(
            cls, 'DISTRO', 'Distribution',
            'Display search results associated with distributions')

    @property
    def filter_terms(self):
        return [PillarName.distribution != None]


class PillarVocabularyBase(NamedSQLObjectHugeVocabulary):
    """Active `IPillar` objects vocabulary."""
    displayname = 'Needs to be overridden'
    _table = PillarName
    _limit = 100

    PROJECT_FILTER = VocabularyFilterProject()
    PROJECTGROUP_FILTER = VocabularyFilterProjectGroup()
    DISTRO_FILTER = VocabularyFilterDistribution()

    def supportedFilters(self):
        return [self.ALL_FILTER]

    def toTerm(self, obj):
        """See `IVocabulary`."""
        if type(obj) == int:
            return self.toTerm(PillarName.get(obj))
        if IPillarName.providedBy(obj):
            assert obj.active, 'Inactive object %s %d' % (
                    obj.__class__.__name__, obj.id)
            obj = obj.pillar

        title = '%s' % obj.title
        return SimpleTerm(obj, obj.name, title)

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        # Pillar names are always lowercase.
        return super(PillarVocabularyBase, self).getTermByToken(
            token.lower())

    def __contains__(self, obj):
        raise NotImplementedError

    def searchForTerms(self, query=None, vocab_filter=None):
        if not query:
            return self.emptySelectResults()
        query = ensure_unicode(query).lower()
        store = IStore(PillarName)
        equal_clauses = [PillarName.name == query]
        like_clauses = [
            PillarName.name != query, PillarName.name.contains_string(query)]
        if self._filter:
            equal_clauses.extend(self._filter)
            like_clauses.extend(self._filter)
        if vocab_filter:
            equal_clauses.extend(vocab_filter.filter_terms)
            like_clauses.extend(vocab_filter.filter_terms)
        ranked_results = store.execute(
            Union(
                Select(
                    (PillarName.id, PillarName.name, SQL('100 AS rank')),
                    tables=[PillarName],
                    where=And(*equal_clauses)),
                Select(
                    (PillarName.id, PillarName.name, SQL('50 AS rank')),
                    tables=[PillarName],
                    where=And(*like_clauses)),
                limit=self._limit, order_by=(
                    Desc(SQL('rank')), PillarName.name), all=True))
        results = [row[0] for row in list(ranked_results)]
        return self.iterator(len(results), results, self.toTerm)


class DistributionOrProductVocabulary(PillarVocabularyBase):
    """Active `IDistribution` or `IProduct` objects vocabulary."""
    displayname = 'Select a project'
    _filter = [PillarName.project == None, PillarName.active == True]

    def __contains__(self, obj):
        if IProduct.providedBy(obj):
            # Only active products are in the vocabulary.
            return obj.active
        else:
            return IDistribution.providedBy(obj)

    def supportedFilters(self):
        return [
            self.ALL_FILTER,
            self.PROJECT_FILTER,
            self.DISTRO_FILTER]


class DistributionOrProductOrProjectGroupVocabulary(PillarVocabularyBase):
    """Active `IProduct`, `IProjectGroup` or `IDistribution` vocabulary."""
    displayname = 'Select a project'
    _filter = [PillarName.active == True]

    def __contains__(self, obj):
        if IProduct.providedBy(obj) or IProjectGroup.providedBy(obj):
            # Only active products and projects are in the vocabulary.
            return obj.active
        else:
            return IDistribution.providedBy(obj)

    def supportedFilters(self):
        return [
            self.ALL_FILTER,
            self.PROJECT_FILTER,
            self.PROJECTGROUP_FILTER,
            self.DISTRO_FILTER]


class FeaturedProjectVocabulary(
                               DistributionOrProductOrProjectGroupVocabulary):
    """Vocabulary of projects that are featured on the LP Home Page."""

    _filter = AND(PillarName.q.id == FeaturedProject.q.pillar_name,
                  PillarName.q.active == True)
    _clauseTables = ['FeaturedProject']

    def __contains__(self, obj):
        """See `IVocabulary`."""
        query = """PillarName.id=FeaturedProject.pillar_name
                   AND PillarName.name = %s""" % sqlvalues(obj.name)
        return PillarName.selectOne(
                   query, clauseTables=['FeaturedProject']) is not None


class SourcePackageNameIterator(BatchedCountableIterator):
    """A custom iterator for SourcePackageNameVocabulary.

    Used to iterate over vocabulary items and provide full
    descriptions.

    Note that the reason we use special iterators is to ensure that we
    only do the search for descriptions across source package names that
    we actually are attempting to list, taking advantage of the
    resultset slicing that BatchNavigator does.
    """

    def getTermsWithDescriptions(self, results):
        return [SimpleTerm(obj, obj.name, obj.name) for obj in results]


class SourcePackageNameVocabulary(NamedSQLObjectHugeVocabulary):
    """A vocabulary that lists source package names."""
    displayname = 'Select a source package'
    _table = SourcePackageName
    _orderBy = 'name'
    iterator = SourcePackageNameIterator

    def getTermByToken(self, token):
        """See `IVocabularyTokenized`."""
        # package names are always lowercase.
        return super(SourcePackageNameVocabulary, self).getTermByToken(
            token.lower())
