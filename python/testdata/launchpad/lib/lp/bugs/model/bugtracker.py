# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BugTracker',
    'BugTrackerAlias',
    'BugTrackerAliasSet',
    'BugTrackerComponent',
    'BugTrackerComponentGroup',
    'BugTrackerSet',
    ]

from datetime import datetime
from itertools import chain
# splittype is not formally documented, but is in urllib.__all__, is
# simple, and is heavily used by the rest of urllib, hence is unlikely
# to change or go away.
from urllib import (
    quote,
    splittype,
    )

from lazr.uri import URI
from pytz import timezone
from sqlobject import (
    BoolCol,
    ForeignKey,
    OR,
    SQLMultipleJoin,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    Count,
    Desc,
    Not,
    SQL,
    )
from storm.locals import (
    Bool,
    Int,
    Reference,
    ReferenceSet,
    Unicode,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.email import valid_email
from lp.app.validators.name import sanitize_name
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTracker,
    IBugTrackerAlias,
    IBugTrackerAliasSet,
    IBugTrackerComponent,
    IBugTrackerComponentGroup,
    IBugTrackerSet,
    SINGLE_PRODUCT_BUGTRACKERTYPES,
    )
from lp.bugs.interfaces.bugtrackerperson import BugTrackerPersonAlreadyExists
from lp.bugs.model.bug import Bug
from lp.bugs.model.bugmessage import BugMessage
from lp.bugs.model.bugtrackerperson import BugTrackerPerson
from lp.bugs.model.bugwatch import BugWatch
from lp.registry.interfaces.person import (
    IPersonSet,
    validate_public_person,
    )
from lp.registry.model.product import (
    Product,
    ProductSet,
    )
from lp.registry.model.projectgroup import ProjectGroup
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    flush_database_updates,
    SQLBase,
    )
from lp.services.database.stormbase import StormBase
from lp.services.helpers import shortlist


def normalise_leading_slashes(rest):
    """Ensure that the 'rest' segment of a URL starts with //."""
    return '//' + rest.lstrip('/')


def normalise_base_url(base_url):
    """Convert https to http, and normalise scheme for others."""
    schema, rest = splittype(base_url)
    if schema == 'https':
        return 'http:' + rest
    elif schema is None:
        return 'http:' + normalise_leading_slashes(base_url)
    else:
        return '%s:%s' % (schema, rest)


def base_url_permutations(base_url):
    """Return all the possible variants of a base URL.

    Sometimes the URL ends with slash, sometimes not. Sometimes http
    is used, sometimes https. This gives a list of all possible
    variants, so that queryByBaseURL can match a base URL, even if it
    doesn't match exactly what is stored in the database.

    >>> base_url_permutations('http://foo/bar')
    ['http://foo/bar', 'http://foo/bar/',
     'https://foo/bar', 'https://foo/bar/']
    """
    http_schemas = ['http', 'https']
    url_schema, rest = splittype(base_url)
    if url_schema in http_schemas or url_schema is None:
        possible_schemas = http_schemas
        rest = normalise_leading_slashes(rest)
    else:
        # This else-clause is here since we have no strict
        # requirement that bug trackers have to have http URLs.
        possible_schemas = [url_schema]
    alternative_urls = [base_url]
    for schema in possible_schemas:
        url = "%s:%s" % (schema, rest)
        if url != base_url:
            alternative_urls.append(url)
        if url.endswith('/'):
            alternative_urls.append(url[:-1])
        else:
            alternative_urls.append(url + '/')
    return alternative_urls


def make_bugtracker_name(uri):
    """Return a name string for a bug tracker based on a URI.

    :param uri: The base URI to be used to identify the bug tracker,
        e.g. http://bugs.example.com or mailto:bugs@example.com
    """
    base_uri = URI(uri)
    if base_uri.scheme == 'mailto':
        if valid_email(base_uri.path):
            base_name = base_uri.path.split('@', 1)[0]
        else:
            raise AssertionError(
                'Not a valid email address: %s' % base_uri.path)
    else:
        base_name = base_uri.host

    return 'auto-%s' % sanitize_name(base_name)


def make_bugtracker_title(uri):
    """Return a title string for a bug tracker based on a URI.

    :param uri: The base URI to be used to identify the bug tracker,
        e.g. http://bugs.example.com or mailto:bugs@example.com
    """
    base_uri = URI(uri)
    if base_uri.scheme == 'mailto':
        if valid_email(base_uri.path):
            local_part, domain = base_uri.path.split('@', 1)
            domain_parts = domain.split('.')
            return 'Email to %s@%s' % (local_part, domain_parts[0])
        else:
            raise AssertionError(
                'Not a valid email address: %s' % base_uri.path)
    else:
        return base_uri.host + base_uri.path


class BugTrackerComponent(StormBase):
    """The software component in the remote bug tracker.

    Most bug trackers organize bug reports by the software 'component'
    they affect.  This class provides a mapping of this upstream component
    to the corresponding source package in the distro.
    """
    implements(IBugTrackerComponent)
    __storm_table__ = 'BugTrackerComponent'

    id = Int(primary=True)
    name = Unicode(allow_none=False)

    component_group_id = Int('component_group')
    component_group = Reference(
        component_group_id,
        'BugTrackerComponentGroup.id')

    is_visible = Bool(allow_none=False)
    is_custom = Bool(allow_none=False)

    distribution_id = Int('distribution')
    distribution = Reference(
        distribution_id,
        'Distribution.id')

    source_package_name_id = Int('source_package_name')
    source_package_name = Reference(
        source_package_name_id,
        'SourcePackageName.id')

    def _get_distro_source_package(self):
        """Retrieves the corresponding source package"""
        if self.distribution is None or self.source_package_name is None:
            return None
        return self.distribution.getSourcePackage(
            self.source_package_name)

    def _set_distro_source_package(self, dsp):
        """Links this component to its corresponding source package"""
        if dsp is None:
            self.distribution = None
            self.source_package_name = None
        else:
            self.distribution = dsp.distribution
            self.source_package_name = dsp.sourcepackagename

    distro_source_package = property(
        _get_distro_source_package,
        _set_distro_source_package,
        None,
        """The distribution's source package for this component""")


class BugTrackerComponentGroup(StormBase):
    """A collection of components in a remote bug tracker.

    Some bug trackers organize sets of components into higher level
    groups, such as Bugzilla's 'product'.
    """
    implements(IBugTrackerComponentGroup)
    __storm_table__ = 'BugTrackerComponentGroup'

    id = Int(primary=True)
    name = Unicode(allow_none=False)
    bug_tracker_id = Int('bug_tracker')
    bug_tracker = Reference(bug_tracker_id, 'BugTracker.id')
    components = ReferenceSet(
        id,
        BugTrackerComponent.component_group_id,
        order_by=BugTrackerComponent.name)

    def addComponent(self, component_name):
        """Adds a component that is synced from a remote bug tracker"""

        component = BugTrackerComponent()
        component.name = component_name
        component.component_group = self

        store = IStore(BugTrackerComponent)
        store.add(component)
        store.flush()

        return component

    def getComponent(self, component_name):
        """Retrieves a component by the given name or id number.

        None is returned if there is no component by that name in the
        group.
        """

        if component_name is None:
            return None
        elif component_name.isdigit():
            component_id = int(component_name)
            return Store.of(self).find(
                BugTrackerComponent,
                BugTrackerComponent.id == component_id,
                BugTrackerComponent.component_group == self.id).one()
        else:
            return Store.of(self).find(
                BugTrackerComponent,
                BugTrackerComponent.name == component_name,
                BugTrackerComponent.component_group == self.id).one()

    def addCustomComponent(self, component_name):
        """Adds a component locally that isn't synced from a remote tracker
        """

        component = BugTrackerComponent()
        component.name = component_name
        component.component_group = self
        component.is_custom = True

        store = IStore(BugTrackerComponent)
        store.add(component)
        store.flush()

        return component


class BugTracker(SQLBase):
    """A class to access the BugTracker table in the database.

    Each BugTracker is a distinct instance of that bug tracking
    tool. For example, each Bugzilla deployment is a separate
    BugTracker. bugzilla.mozilla.org and bugzilla.gnome.org are each
    distinct BugTrackers.
    """
    implements(IBugTracker)

    _table = 'BugTracker'

    bugtrackertype = EnumCol(
        dbName='bugtrackertype', schema=BugTrackerType, notNull=True)
    name = StringCol(notNull=True, unique=True)
    title = StringCol(notNull=True)
    summary = StringCol(notNull=False)
    baseurl = StringCol(notNull=True)
    active = Bool(
        name='active', allow_none=False, default=True)

    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    contactdetails = StringCol(notNull=False)
    has_lp_plugin = BoolCol(notNull=False, default=False)
    products = SQLMultipleJoin(
        'Product', joinColumn='bugtracker', orderBy='name')
    watches = SQLMultipleJoin(
        'BugWatch', joinColumn='bugtracker', orderBy='-datecreated',
        prejoins=['bug'])

    _filing_url_patterns = {
        BugTrackerType.BUGZILLA: (
            "%(base_url)s/enter_bug.cgi?product=%(remote_product)s"
            "&short_desc=%(summary)s&long_desc=%(description)s"),
        BugTrackerType.GOOGLE_CODE: (
            "%(base_url)s/entry?summary=%(summary)s&"
            "comment=%(description)s"),
        BugTrackerType.MANTIS: (
            "%(base_url)s/bug_report_advanced_page.php"
            "?summary=%(summary)s&description=%(description)s"),
        BugTrackerType.PHPPROJECT: (
            "%(base_url)s/report.php"
            "?in[sdesc]=%(summary)s&in[ldesc]=%(description)s"),
        BugTrackerType.ROUNDUP: (
            "%(base_url)s/issue?@template=item&title=%(summary)s"
            "&@note=%(description)s"),
        BugTrackerType.RT: (
            "%(base_url)s/Ticket/Create.html?Queue=%(remote_product)s"
            "&Subject=%(summary)s&Content=%(description)s"),
        BugTrackerType.SAVANE: (
            "%(base_url)s/bugs/?func=additem&group=%(remote_product)s"),
        BugTrackerType.SOURCEFORGE: (
            "%(base_url)s/%(tracker)s/?func=add&"
            "group_id=%(group_id)s&atid=%(at_id)s"),
        BugTrackerType.TRAC: (
            "%(base_url)s/newticket?summary=%(summary)s&"
            "description=%(description)s"),
        }

    _search_url_patterns = {
        BugTrackerType.BUGZILLA: (
            "%(base_url)s/query.cgi?product=%(remote_product)s"
            "&short_desc=%(summary)s"),
        BugTrackerType.GOOGLE_CODE: "%(base_url)s/list?q=%(summary)s",
        BugTrackerType.DEBBUGS: (
            "%(base_url)s/cgi-bin/search.cgi?phrase=%(summary)s"
            "&attribute_field=package&attribute_operator=STROREQ"
            "&attribute_value=%(remote_product)s"),
        BugTrackerType.MANTIS: "%(base_url)s/view_all_bug_page.php",
        BugTrackerType.PHPPROJECT: (
            "%(base_url)s/search.php?search_for=%(summary)s"),
        BugTrackerType.ROUNDUP: (
            "%(base_url)s/issue?@template=search&@search_text=%(summary)s"),
        BugTrackerType.RT: (
            "%(base_url)s/Search/Build.html?Query=Queue = "
            "'%(remote_product)s' AND Subject LIKE '%(summary)s'"),
        BugTrackerType.SAVANE: (
            "%(base_url)s/bugs/?func=search&group=%(remote_product)s"),
        BugTrackerType.SOURCEFORGE: (
            "%(base_url)s/search/?group_id=%(group_id)s"
            "&some_word=%(summary)s&type_of_search=artifact"),
        BugTrackerType.TRAC: "%(base_url)s/search?ticket=on&q=%(summary)s",
        }

    @property
    def _custom_filing_url_patterns(self):
        """Return a dict of bugtracker-specific bugfiling URL patterns."""
        gnome_bugzilla = getUtility(ILaunchpadCelebrities).gnome_bugzilla
        return {
            gnome_bugzilla: (
                "%(base_url)s/enter_bug.cgi?product=%(remote_product)s"
                "&short_desc=%(summary)s&comment=%(description)s"),
            }

    @property
    def latestwatches(self):
        """See `IBugTracker`."""
        return self.watches[:10]

    @property
    def multi_product(self):
        """Return True if this BugTracker tracks multiple projects."""
        if self.bugtrackertype not in SINGLE_PRODUCT_BUGTRACKERTYPES:
            return True
        else:
            return False

    def getBugFilingAndSearchLinks(self, remote_product, summary=None,
                                   description=None, remote_component=None):
        """See `IBugTracker`."""
        bugtracker_urls = {'bug_filing_url': None, 'bug_search_url': None}

        if remote_product is None and self.multi_product:
            # Don't try to return anything if remote_product is required
            # for this BugTrackerType and one hasn't been passed.
            return bugtracker_urls

        if remote_product is None:
            # Turn the remote product into an empty string so that
            # quote() doesn't blow up later on.
            remote_product = ''

        if remote_component is None:
            # Ditto for remote component.
            remote_component = ''

        if self in self._custom_filing_url_patterns:
            # Some bugtrackers are customised to accept different
            # querystring parameters from the default. We special-case
            # these.
            bug_filing_pattern = self._custom_filing_url_patterns[self]
        else:
            bug_filing_pattern = self._filing_url_patterns.get(
                self.bugtrackertype, None)

        bug_search_pattern = self._search_url_patterns.get(
            self.bugtrackertype, None)

        # Make sure that we don't put > 1 '/' in returned URLs.
        base_url = self.baseurl.rstrip('/')

        # If summary or description are None, convert them to empty
        # strings to that we don't try to pass anything to the upstream
        # bug tracker.
        if summary is None:
            summary = ''
        if description is None:
            description = ''

        # UTF-8 encode the description and summary so that quote()
        # doesn't break if they contain unicode characters it doesn't
        # understand.
        summary = summary.encode('utf-8')
        description = description.encode('utf-8')

        if self.bugtrackertype == BugTrackerType.SOURCEFORGE:
            try:
                # SourceForge bug trackers use a group ID and an ATID to
                # file a bug, rather than a product name. remote_product
                # should be an ampersand-separated string in the form
                # 'group_id&atid'
                group_id, at_id = remote_product.split('&')
            except ValueError:
                # If remote_product contains something that's not valid
                # in a SourceForge context we just return early.
                return None

            # If this bug tracker is the SourceForge celebrity the link
            # is to the new bug tracker rather than the old one.
            sf_celeb = getUtility(ILaunchpadCelebrities).sourceforge_tracker
            if self == sf_celeb:
                tracker = 'tracker2'
            else:
                tracker = 'tracker'

            url_components = {
                'base_url': base_url,
                'tracker': quote(tracker),
                'group_id': quote(group_id),
                'at_id': quote(at_id),
                'summary': quote(summary),
                'description': quote(description),
                }

        else:
            url_components = {
                'base_url': base_url,
                'remote_product': quote(remote_product),
                'remote_component': quote(remote_component),
                'summary': quote(summary),
                'description': quote(description),
                }

        if bug_filing_pattern is not None:
            bugtracker_urls['bug_filing_url'] = (
                bug_filing_pattern % url_components)
        if bug_search_pattern is not None:
            bugtracker_urls['bug_search_url'] = (
                bug_search_pattern % url_components)

        return bugtracker_urls

    def getBugsWatching(self, remotebug):
        """See `IBugTracker`."""
        # We special-case email address bug trackers. Since we don't
        # record a remote bug id for them we can never know which bugs
        # are already watching a remote bug.
        if self.bugtrackertype == BugTrackerType.EMAILADDRESS:
            return []
        return shortlist(
            Store.of(self).find(
                Bug,
                BugWatch.bugID == Bug.id, BugWatch.bugtrackerID == self.id,
                BugWatch.remotebug == remotebug).config(
                    distinct=True).order_by(Bug.datecreated))

    @property
    def watches_ready_to_check(self):
        return Store.of(self).find(
            BugWatch,
            BugWatch.bugtracker == self,
            Not(BugWatch.next_check == None),
            BugWatch.next_check <= datetime.now(timezone('UTC')))

    @property
    def watches_with_unpushed_comments(self):
        return Store.of(self).find(
            BugWatch,
            BugWatch.bugtracker == self,
            BugMessage.bugwatch == BugWatch.id,
            BugMessage.remote_comment_id == None).config(distinct=True)

    @property
    def watches_needing_update(self):
        """All watches needing some sort of update.

        :return: The union of `watches_ready_to_check` and
            `watches_with_unpushed_comments`.
        """
        return self.watches_ready_to_check.union(
            self.watches_with_unpushed_comments)

    # Join to return a list of BugTrackerAliases relating to this
    # BugTracker.
    _bugtracker_aliases = SQLMultipleJoin(
        'BugTrackerAlias', joinColumn='bugtracker')

    def _get_aliases(self):
        """See `IBugTracker.aliases`."""
        alias_urls = set(alias.base_url for alias in self._bugtracker_aliases)
        # Although it does no harm if the current baseurl is also an
        # alias, we hide it and all its permutations to avoid
        # confusion.
        alias_urls.difference_update(base_url_permutations(self.baseurl))
        return tuple(sorted(alias_urls))

    def _set_aliases(self, alias_urls):
        """See `IBugTracker.aliases`."""
        if alias_urls is None:
            alias_urls = set()
        else:
            alias_urls = set(alias_urls)

        current_aliases_by_url = dict(
            (alias.base_url, alias) for alias in self._bugtracker_aliases)
        # Make a set of the keys, i.e. a set of current URLs.
        current_alias_urls = set(current_aliases_by_url)

        # URLs we need to add as aliases.
        to_add = alias_urls - current_alias_urls
        # URL aliases we need to delete.
        to_del = current_alias_urls - alias_urls

        for url in to_add:
            BugTrackerAlias(bugtracker=self, base_url=url)
        for url in to_del:
            alias = current_aliases_by_url[url]
            alias.destroySelf()

    aliases = property(
        _get_aliases, _set_aliases, None,
        """A list of the alias URLs. See `IBugTracker`.

        The aliases are found by querying BugTrackerAlias. Assign an
        iterable of URLs or None to set or remove aliases.
        """)

    @property
    def imported_bug_messages(self):
        """See `IBugTracker`."""
        return Store.of(self).find(
            BugMessage,
            BugMessage.bugwatchID == BugWatch.id,
            BugWatch.bugtrackerID == self.id).order_by(BugMessage.id)

    def getLinkedPersonByName(self, name):
        """Return the Person with a given name on this bugtracker."""
        return BugTrackerPerson.selectOneBy(name=name, bugtracker=self)

    def linkPersonToSelf(self, name, person):
        """See `IBugTrackerSet`."""
        # Check that this name isn't already in use for this bugtracker.
        if self.getLinkedPersonByName(name) is not None:
            raise BugTrackerPersonAlreadyExists(
                "Name '%s' is already in use for bugtracker '%s'." %
                (name, self.name))

        bugtracker_person = BugTrackerPerson(
            name=name, bugtracker=self, person=person)

        return bugtracker_person

    def ensurePersonForSelf(
        self, display_name, email, rationale, creation_comment):
        """Return a Person that is linked to this bug tracker."""
        # If we have an email address to work with we can use
        # ensurePerson() to get the Person we need.
        if email is not None:
            return getUtility(IPersonSet).ensurePerson(
                email, display_name, rationale, creation_comment)

        # First, see if there's already a BugTrackerPerson for this
        # display_name on this bugtracker. If there is, return it.
        bugtracker_person = self.getLinkedPersonByName(display_name)

        if bugtracker_person is not None:
            return bugtracker_person.person

        # Generate a valid Launchpad name for the Person.
        base_canonical_name = (
            "%s-%s" % (sanitize_name(display_name), self.name))
        canonical_name = base_canonical_name

        person_set = getUtility(IPersonSet)
        index = 0
        while person_set.getByName(canonical_name) is not None:
            index += 1
            canonical_name = "%s-%s" % (base_canonical_name, index)

        person = person_set.createPersonWithoutEmail(
            canonical_name, rationale, creation_comment,
            displayname=display_name)

        # Link the Person to the bugtracker for future reference.
        bugtracker_person = self.linkPersonToSelf(display_name, person)

        return person

    def resetWatches(self, new_next_check=None):
        """See `IBugTracker`."""
        if new_next_check is None:
            new_next_check = SQL(
                "now() at time zone 'UTC' + (random() * interval '1 day')")

        store = Store.of(self)
        store.find(BugWatch, BugWatch.bugtracker == self).set(
            next_check=new_next_check, lastchecked=None,
            last_error_type=None)

    def addRemoteComponentGroup(self, component_group_name):
        """See `IBugTracker`."""

        if component_group_name is None:
            component_group_name = "default"
        component_group = BugTrackerComponentGroup()
        component_group.name = component_group_name
        component_group.bug_tracker = self

        store = IStore(BugTrackerComponentGroup)
        store.add(component_group)
        store.commit()

        return component_group

    def getAllRemoteComponentGroups(self):
        """See `IBugTracker`."""
        component_groups = []

        component_groups = Store.of(self).find(
            BugTrackerComponentGroup,
            BugTrackerComponentGroup.bug_tracker == self.id)
        component_groups = component_groups.order_by(
            BugTrackerComponentGroup.name)
        return component_groups

    def getRemoteComponentGroup(self, component_group_name):
        """See `IBugTracker`."""
        component_group = None
        store = IStore(BugTrackerComponentGroup)
        if component_group_name is None:
            return None
        elif component_group_name.isdigit():
            component_group_id = int(component_group_name)
            component_group = store.find(
                BugTrackerComponentGroup,
                BugTrackerComponentGroup.id == component_group_id).one()
        else:
            component_group = store.find(
                BugTrackerComponentGroup,
                BugTrackerComponentGroup.name == component_group_name).one()
        return component_group

    def getRemoteComponentForDistroSourcePackageName(
        self, distribution, sourcepackagename):
        """See `IBugTracker`."""
        if distribution is None:
            return None
        dsp = distribution.getSourcePackage(sourcepackagename)
        if dsp is None:
            return None
        return Store.of(self).find(
            BugTrackerComponent,
            BugTrackerComponent.distribution == distribution.id,
            BugTrackerComponent.source_package_name ==
                dsp.sourcepackagename.id).one()

    def getRelatedPillars(self, user=None):
        """See `IBugTracker`."""
        products = IStore(Product).find(
            Product,
            Product.bugtrackerID == self.id, Product.active == True,
            ProductSet.getProductPrivacyFilter(user)).order_by(Product.name)
        groups = IStore(ProjectGroup).find(
            ProjectGroup,
            ProjectGroup.bugtrackerID == self.id,
            ProjectGroup.active == True).order_by(ProjectGroup.name)
        return groups, products


class BugTrackerSet:
    """Implements IBugTrackerSet for a container or set of BugTrackers,
    either the full set in the db, or a subset.
    """

    implements(IBugTrackerSet)

    table = BugTracker

    def __init__(self):
        self.title = 'Bug trackers registered in Launchpad'

    def get(self, bugtracker_id, default=None):
        """See `IBugTrackerSet`."""
        try:
            return BugTracker.get(bugtracker_id)
        except SQLObjectNotFound:
            return default

    def getByName(self, name, default=None):
        """See `IBugTrackerSet`."""
        return self.table.selectOne(self.table.q.name == name)

    def __getitem__(self, name):
        item = self.table.selectOne(self.table.q.name == name)
        if item is None:
            raise NotFoundError(name)
        else:
            return item

    def __iter__(self):
        for row in self.table.select(orderBy="title"):
            yield row

    def queryByBaseURL(self, baseurl):
        """See `IBugTrackerSet`."""
        # All permutations we'll search for.
        permutations = base_url_permutations(baseurl)
        # Construct the search. All the important parts in the next
        # expression are lazily evaluated. SQLObject queries do not
        # execute any SQL until results are pulled, so the first query
        # to return a match will be the last query executed.
        matching_bugtrackers = chain(
            # Search for any permutation in BugTracker.
            BugTracker.select(
                OR(*(BugTracker.q.baseurl == url
                     for url in permutations))),
            # Search for any permutation in BugTrackerAlias.
            (alias.bugtracker for alias in
             BugTrackerAlias.select(
                    OR(*(BugTrackerAlias.q.base_url == url
                         for url in permutations)))))
        # Return the first match.
        for bugtracker in matching_bugtrackers:
            return bugtracker
        return None

    def search(self):
        """See `IBugTrackerSet`."""
        return BugTracker.select()

    def getAllTrackers(self, active=None):
        if active is not None:
            clauses = [BugTracker.active == active]
        else:
            clauses = []
        return IStore(BugTracker).find(BugTracker, *clauses).order_by(
            BugTracker.name)

    def ensureBugTracker(self, baseurl, owner, bugtrackertype, title=None,
                         summary=None, contactdetails=None, name=None):
        """See `IBugTrackerSet`."""
        # Try to find an existing bug tracker that matches.
        bugtracker = self.queryByBaseURL(baseurl)
        if bugtracker is not None:
            return bugtracker
        # Create the bugtracker; we don't know about it.
        if name is None:
            base_name = make_bugtracker_name(baseurl)
            # If we detect that this name exists already we mutate it
            # until it doesn't.
            name = base_name
            name_increment = 1
            while self.getByName(name) is not None:
                name = "%s-%d" % (base_name, name_increment)
                name_increment += 1
        if title is None:
            title = make_bugtracker_title(baseurl)
        bugtracker = BugTracker(
            name=name, bugtrackertype=bugtrackertype,
            title=title, summary=summary, baseurl=baseurl,
            contactdetails=contactdetails, owner=owner)
        flush_database_updates()
        return bugtracker

    @property
    def count(self):
        return IStore(self.table).find(self.table).count()

    @property
    def names(self):
        return IStore(self.table).find(self.table).values(self.table.name)

    def getMostActiveBugTrackers(self, limit=None):
        """See `IBugTrackerSet`."""
        return IStore(BugTracker).find(
            BugTracker,
            BugTracker.id == BugWatch.bugtrackerID).group_by(
                BugTracker).order_by(Desc(Count(BugWatch))).config(limit=limit)

    def getPillarsForBugtrackers(self, bugtrackers, user=None):
        """See `IBugTrackerSet`."""
        ids = [tracker.id for tracker in bugtrackers]
        products = IStore(Product).find(
            Product,
            Product.bugtrackerID.is_in(ids), Product.active == True,
            ProductSet.getProductPrivacyFilter(user)).order_by(Product.name)
        groups = IStore(ProjectGroup).find(
            ProjectGroup,
            ProjectGroup.bugtrackerID.is_in(ids),
            ProjectGroup.active == True).order_by(ProjectGroup.name)
        results = {}
        for product in products:
            results.setdefault(product.bugtracker, []).append(product)
        for project in groups:
            results.setdefault(project.bugtracker, []).append(project)
        return results


class BugTrackerAlias(SQLBase):
    """See `IBugTrackerAlias`."""
    implements(IBugTrackerAlias)

    bugtracker = ForeignKey(
        foreignKey="BugTracker", dbName="bugtracker", notNull=True)
    base_url = StringCol(notNull=True)


class BugTrackerAliasSet:
    """See `IBugTrackerAliasSet`."""
    implements(IBugTrackerAliasSet)

    table = BugTrackerAlias

    def queryByBugTracker(self, bugtracker):
        """See IBugTrackerSet."""
        return self.table.selectBy(bugtracker=bugtracker.id)
