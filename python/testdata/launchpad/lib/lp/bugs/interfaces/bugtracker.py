# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug tracker interfaces."""

__metaclass__ = type

__all__ = [
    'BugTrackerType',
    'IBugTracker',
    'IBugTrackerAlias',
    'IBugTrackerAliasSet',
    'IBugTrackerComponent',
    'IBugTrackerComponentGroup',
    'IBugTrackerSet',
    'IHasExternalBugTracker',
    'IRemoteBug',
    'SINGLE_PRODUCT_BUGTRACKERTYPES',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_factory_operation,
    export_read_operation,
    export_write_operation,
    exported,
    operation_for_version,
    operation_parameters,
    operation_returns_collection_of,
    operation_returns_entry,
    rename_parameters_as,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    )
from zope.component import getUtility
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Choice,
    Int,
    List,
    Object,
    Text,
    TextLine,
    )
from zope.schema.interfaces import IObject

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.name import name_validator
from lp.services.fields import (
    ContentNameField,
    StrippedTextLine,
    URIField,
    )
from lp.services.webservice.apihelpers import patch_reference_property


LOCATION_SCHEMES_ALLOWED = 'http', 'https', 'mailto'


class BugTrackerNameField(ContentNameField):

    errormessage = _("%s is already in use by another bugtracker.")

    @property
    def _content_iface(self):
        return IBugTracker

    def _getByName(self, name):
        return getUtility(IBugTrackerSet).getByName(name)


class BugTrackerURL(URIField):
    """A bug tracker URL that's not used by any other bug trackers.

    When checking if the URL is already registered with another
    bugtracker, it takes into account that the URL may differ slightly,
    i.e. it could end with a slash or be https instead of http.
    """

    def _validate(self, input):
        """Check that the URL is not already in use by another bugtracker."""
        super(BugTrackerURL, self)._validate(input)
        bugtracker = getUtility(IBugTrackerSet).queryByBaseURL(input)
        if bugtracker is not None and bugtracker != self.context:
            raise LaunchpadValidationError(
                '%s is already registered in Launchpad as "%s" (%s).'
                % (input, bugtracker.title, bugtracker.name))


class BugTrackerType(DBEnumeratedType):
    """The Types of BugTracker Supported by Launchpad.

    This enum is used to differentiate between the different types of Bug
    Tracker that are supported by Malone in the Launchpad.
    """

    BUGZILLA = DBItem(1, """
        Bugzilla

        The godfather of open source bug tracking, the Bugzilla system was
        developed for the Mozilla project and is now in widespread use. It
        is big and ugly but also comprehensive.
        """)

    DEBBUGS = DBItem(2, """
        Debbugs

        The debbugs tracker is email based, and allows you to treat every
        bug like a small mailing list.
        """)

    ROUNDUP = DBItem(3, """
        Roundup

        Roundup is a lightweight, customisable and fast web/email based bug
        tracker written in Python.
        """)

    TRAC = DBItem(4, """
        Trac

        Trac is an enhanced wiki and issue tracking system for
        software development projects.
        """)

    SOURCEFORGE = DBItem(5, """
        SourceForge or SourceForge derivative

        SorceForge is a collaborative revision control and software
        development management system. It has several derivatives,
        including GForge, RubyForge, BerliOS and JavaForge.
        """)

    MANTIS = DBItem(6, """
        Mantis

        Mantis is a web-based bug tracking system written in PHP.
        """)

    RT = DBItem(7, """
        Request Tracker (RT)

        RT is a web-based ticketing system written in Perl.
        """)

    EMAILADDRESS = DBItem(8, """
        Email Address

        Bugs are tracked by email, perhaps on a mailing list.
        """)

    SAVANE = DBItem(9, """
        Savane

        Savane is a web-based project hosting system which includes
        support and request tracking. The best-known example of Savane
        is GNU's Savannah.
        """)

    PHPPROJECT = DBItem(10, """
        PHP Project Bugtracker

        The bug tracker developed by the PHP project.
        """)

    GOOGLE_CODE = DBItem(11, """
        Google Code

        Google Code is a project hosting and issue tracking service from
        Google.
        """)


# A list of the BugTrackerTypes that don't need a remote product to be
# able to return a bug filing URL. We use a whitelist rather than a
# blacklist approach here; if it's not in this list LP will assume that
# a remote product is required. This saves us from presenting
# embarrassingly useless URLs to users.
SINGLE_PRODUCT_BUGTRACKERTYPES = [
    BugTrackerType.GOOGLE_CODE,
    BugTrackerType.MANTIS,
    BugTrackerType.PHPPROJECT,
    BugTrackerType.ROUNDUP,
    BugTrackerType.TRAC,
    ]


class IBugTracker(Interface):
    """A remote bug system.

    Launchpadlib example: What bug tracker is used for a distro source
    package?

    ::

        product = source_package.upstream_product
        if product:
            tracker = product.bug_tracker
            if not tracker:
                project = product.project_group
                if project:
                    tracker = project.bug_tracker
        if tracker:
            print "%s at %s" %(tracker.bug_tracker_type, tracker.base_url)

    """
    export_as_webservice_entry()

    id = Int(title=_('ID'))
    bugtrackertype = exported(
        Choice(title=_('Bug Tracker Type'),
               vocabulary=BugTrackerType,
               default=BugTrackerType.BUGZILLA),
        exported_as='bug_tracker_type')
    name = exported(
        BugTrackerNameField(
            title=_('Name'),
            constraint=name_validator,
            description=_('A URL-friendly name for the bug tracker, '
                          'such as "mozilla-bugs".')))
    title = exported(
        TextLine(
            title=_('Title'),
            description=_('A descriptive label for this tracker to show '
                          'in listings.')))
    summary = exported(
        Text(
            title=_('Summary'),
            description=_(
                'A brief introduction or overview of this bug '
                'tracker instance.'),
            required=False))
    baseurl = exported(
        BugTrackerURL(
            title=_('Location'),
            allowed_schemes=LOCATION_SCHEMES_ALLOWED,
            description=_(
                'The top-level URL for the bug tracker, or an upstream email '
                'address. This must be accurate so that Launchpad can link '
                'to external bug reports.')),
        exported_as='base_url')
    aliases = exported(
        List(
            title=_('Location aliases'),
            description=_(
                'A list of URLs or email addresses that all lead to the '
                'same bug tracker, or commonly seen typos, separated by '
                'whitespace.'),
            value_type=BugTrackerURL(
                allowed_schemes=LOCATION_SCHEMES_ALLOWED),
            required=False),
        exported_as='base_url_aliases')
    owner = exported(
        Reference(title=_('Owner'), schema=Interface),
        exported_as='registrant')
    contactdetails = exported(
        Text(
            title=_('Contact details'),
            description=_(
                'The contact details for the external bug tracker (so that, '
                'for example, its administrators can be contacted about a '
                'security breach).'),
            required=False),
        exported_as='contact_details')
    watches = doNotSnapshot(
        exported(
            CollectionField(
                title=_('The remote watches on this bug tracker.'),
                value_type=Reference(schema=IObject))))
    has_lp_plugin = exported(
        Bool(
            title=_('This bug tracker has a Launchpad plugin installed.'),
            required=False, default=False))
    products = Attribute('The products that use this bug tracker.')
    latestwatches = Attribute('The last 10 watches created.')
    imported_bug_messages = Attribute(
        'Bug messages that have been imported from this bug tracker.')
    multi_product = Attribute(
        "This bug tracker tracks multiple remote products.")
    active = exported(
        Bool(
            title=_('Updates for this bug tracker are enabled'),
            required=True, default=True))

    watches_ready_to_check = Attribute(
        "The set of bug watches that are scheduled to be checked.")
    watches_with_unpushed_comments = Attribute(
        "The set of bug watches that have unpushed comments.")
    watches_needing_update = Attribute(
        "The set of bug watches that need updating.")

    def getBugFilingAndSearchLinks(remote_product, summary=None,
                                   description=None, remote_component=None):
        """Return the bug filing and search links for the tracker.

        :param remote_product: The name of the product on which the bug
            is to be filed or searched for.
        :param summary: The string with which to pre-filly the summary
            field of the upstream bug tracker's search and bug filing forms.
        :param description: The string with which to pre-filly the description
            field of the upstream bug tracker's bug filing form.
        :param remote_component: The name of the component on which the bug
            is to be filed or search for.
        :return: A dict of the absolute URL of the bug filing form and
            the search form for `remote_product` on the remote tracker,
            in the form {'bug_filing_url': foo, 'search_url': bar}. If
            either or both of the URLs is unavailable for the current
            BugTrackerType the relevant values in the dict will be set
            to None. If the bug tracker requires a `remote_product` but
            None is passed, None will be returned for both values in the
            dict.
        """

    def getBugsWatching(remotebug):
        """Get the bugs watching the given remote bug in this bug tracker."""

    def getLinkedPersonByName(name):
        """Return the `IBugTrackerPerson` for a given name on a bugtracker.

        :param name: The name of the person on the bugtracker in
            `bugtracker`.
        :return: an `IBugTrackerPerson`.
        """

    def linkPersonToSelf(name, person):
        """Link a Person to the BugTracker using a given name.

        :param name: The name used for person on bugtracker.
        :param person: The `IPerson` to link to bugtracker.
        :raise BugTrackerPersonAlreadyExists: If `name` has already been
            used to link a person to `bugtracker`.
        :return: An `IBugTrackerPerson`.
        """

    def ensurePersonForSelf(
        display_name, email, rationale, creation_comment):
        """Return the correct `IPerson` for a given name on a bugtracker.

        :param bugtracker: The `IBugTracker` for which we should have a
            given Person.
        :param display_name: The name of the Person on `bugtracker`.
        :param email: The Person's email address if available. If `email`
            is supplied a Person will be created or retrieved using that
            email address and no `IBugTrackerPerson` records will be created.
        :param rationale: The `PersonCreationRationale` used to create a
            new `IPerson` for this `name` and `bugtracker`, if necessary.
        :param creation_comment: The creation comment for the `IPerson`
            if one is created.
         """

    def destroySelf():
        """Delete this bug tracker."""

    def resetWatches(new_next_check=None):
        """Reset the next_check times of this BugTracker's `BugWatch`es.

        :param new_next_check: If specified, contains the datetime to
            which to set the BugWatches' next_check times.  If not
            specified, the watches' next_check times will be set to a
            point between now and 24 hours hence.
        """

    @operation_parameters(
        component_group_name=TextLine(
            title=u"The name of the remote component group", required=True))
    @operation_returns_entry(Interface)
    @export_write_operation()
    def addRemoteComponentGroup(component_group_name):
        """Adds a new component group to the bug tracker"""

    @export_read_operation()
    @operation_returns_collection_of(Interface)
    def getAllRemoteComponentGroups():
        """Return collection of all component groups for this bug tracker"""

    @operation_parameters(
        component_group_name=TextLine(
            title=u"The name of the remote component group",
            required=True))
    @operation_returns_entry(Interface)
    @export_read_operation()
    def getRemoteComponentGroup(component_group_name):
        """Retrieve a given component group registered with the bug tracker.

        :param component_group_name: Name of the component group to retrieve.
        """

    @operation_parameters(
        distribution=TextLine(
            title=u"The distribution for the source package",
            required=True),
        sourcepackagename=TextLine(
            title=u"The source package name",
            required=True))
    @operation_returns_entry(Interface)
    @export_read_operation()
    @operation_for_version('devel')
    def getRemoteComponentForDistroSourcePackageName(
        distribution, sourcepackagename):
        """Returns the component linked to this source package, if any.

        If no components have been linked, returns value of None.
        """

    def getRelatedPillars(user=None):
        """Returns the `IProduct`s and `IProjectGroup`s that use this tracker.
        """


class IBugTrackerSet(Interface):
    """A set of IBugTracker's.

    Each BugTracker is a distinct instance of a bug tracking tool. For
    example, bugzilla.mozilla.org is distinct from bugzilla.gnome.org.
    """
    export_as_webservice_collection(IBugTracker)

    title = Attribute('Title')

    count = Attribute("The number of registered bug trackers.")

    names = Attribute("The names of all registered bug trackers.")

    def get(bugtracker_id, default=None):
        """Get a BugTracker by its id.

        If no tracker with the given id exists, return default.
        """

    @operation_parameters(
        name=TextLine(title=u"The bug tracker name", required=True))
    @operation_returns_entry(IBugTracker)
    @export_read_operation()
    def getByName(name, default=None):
        """Get a BugTracker by its name.

        If no tracker with the given name exists, return default.
        """

    def __getitem__(name):
        """Get a BugTracker by its name in the database.

        Note: We do not want to expose the BugTracker.id to the world
        so we use its name.
        """

    def __iter__():
        """Iterate through BugTrackers."""

    @rename_parameters_as(baseurl='base_url')
    @operation_parameters(
        baseurl=TextLine(
            title=u"The base URL of the bug tracker", required=True))
    @operation_returns_entry(IBugTracker)
    @export_read_operation()
    def queryByBaseURL(baseurl):
        """Return one or None BugTracker's by baseurl"""

    @call_with(owner=REQUEST_USER)
    @rename_parameters_as(
        baseurl='base_url', bugtrackertype='bug_tracker_type',
        contactdetails='contact_details')
    @export_factory_operation(
        IBugTracker,
        ['baseurl', 'bugtrackertype', 'title', 'summary',
         'contactdetails', 'name'])
    def ensureBugTracker(baseurl, owner, bugtrackertype,
        title=None, summary=None, contactdetails=None, name=None):
        """Make sure that there is a bugtracker for the given base url.

        If not, create one using the given attributes.
        """

    @collection_default_content()
    def search():
        """Search all the IBugTrackers in the system."""

    def getMostActiveBugTrackers(limit=None):
        """Return the top IBugTrackers.

        Returns a list of IBugTracker objects, ordered by the number
        of bugwatches for each tracker, from highest to lowest.
        """

    def getPillarsForBugtrackers(bug_trackers, user=None):
        """Return dict mapping bugtrackers to lists of pillars."""

    def getAllTrackers(active=None):
        """Return a ResultSet of bugtrackers.

        :param active: If True, only active trackers are returned, if False
            only inactive trackers are returned. All trackers are returned
            by default.
        """


class IBugTrackerAlias(Interface):
    """Another URL for a remote bug system.

    Used to prevent accidental duplication of bugtrackers and so
    reduce the gardening burden.
    """

    id = Int(title=_('ID'))
    bugtracker = Object(
        title=_('The bugtracker for which this is an alias.'),
        schema=IBugTracker)
    base_url = BugTrackerURL(
        title=_('Location'),
        allowed_schemes=LOCATION_SCHEMES_ALLOWED,
        description=_('Another URL or email address for the bug tracker.'))


class IBugTrackerAliasSet(Interface):
    """A set of IBugTrackerAliases."""

    def queryByBugTracker(bugtracker):
        """Query IBugTrackerAliases by BugTracker."""


class IBugTrackerComponent(Interface):
    """The software component in the remote bug tracker.

    Most bug trackers organize bug reports by the software 'component'
    they affect.  This class provides a mapping of this upstream component
    to the corresponding source package in the distro.
    """
    export_as_webservice_entry()

    id = Int(title=_('ID'), required=True, readonly=True)
    is_visible = exported(Bool(
        title=_('Is Visible?'),
        description=_("Should the component be shown in "
                      "the Launchpad web interface?"),
        ))
    is_custom = Bool(
        title=_('Is Custom?'),
        description=_("Was the component added locally in "
                      "Launchpad?  If it was, we must retain "
                      "it across updates of bugtracker data."),
        readonly=True)

    name = exported(
        Text(
            title=_('Name'),
            description=_("The name of a software component "
                          "as shown in Launchpad.")))
    sourcepackagename = Choice(
        title=_("Package"), required=False, vocabulary='SourcePackageName')
    distribution = Choice(
        title=_("Distribution"), required=False, vocabulary='Distribution')

    distro_source_package = exported(
        Reference(
            Interface,
            title=_("Distribution Source Package"),
            description=_("The distribution source package object that "
                          "should be linked to this component."),
            required=False))

    component_group = exported(
        Reference(title=_('Component Group'), schema=Interface))


class IBugTrackerComponentGroup(Interface):
    """A collection of components in a remote bug tracker.

    Some bug trackers organize sets of components into higher level groups,
    such as Bugzilla's 'product'.
    """
    export_as_webservice_entry()

    id = Int(title=_('ID'))
    name = exported(
        Text(
            title=_('Name'),
            description=_('The name of the bug tracker product.')))
    components = exported(
        CollectionField(
            title=_('Components.'),
            value_type=Reference(schema=IBugTrackerComponent)))
    bug_tracker = exported(
        Reference(title=_('BugTracker'), schema=IBugTracker))

    @operation_parameters(
        component_name=TextLine(
            title=u"The name of the remote software component to be added",
            required=True))
    @export_write_operation()
    def addComponent(component_name):
        """Adds a component to be tracked as part of this component group"""


# Patch in a mutual reference between IBugTrackerComponent and
# IBugTrackerComponentGroup.
patch_reference_property(
    IBugTrackerComponent, "component_group", IBugTrackerComponentGroup)


class IHasExternalBugTracker(Interface):
    """An object that can have an external bugtracker specified."""

    def getExternalBugTracker():
        """Return the external bug tracker used by this bug tracker.

        If the product uses Launchpad, return None.

        If the product doesn't have a bug tracker specified, return the
        project bug tracker instead. If the product doesn't belong to a
        superproject, or if the superproject doesn't have a bug tracker,
        return None.
        """


class IRemoteBug(Interface):
    """A remote bug for a given bug tracker."""

    bugtracker = Choice(title=_('Bug System'), required=True,
        vocabulary='BugTracker', description=_("The bug tracker in which "
        "the remote bug is found."))

    remotebug = StrippedTextLine(title=_('Remote Bug'), required=True,
        readonly=False, description=_("The bug number of this bug in the "
        "remote bug system."))

    bugs = Attribute(
        _("A list of the Launchpad bugs watching the remote bug."))

    title = TextLine(
        title=_('Title'),
        description=_('A descriptive label for this remote bug'))
