# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""ProjectGroup-related interfaces for Launchpad."""

__metaclass__ = type

__all__ = [
    'IProjectGroup',
    'IProjectGroupPublic',
    'IProjectGroupSeries',
    'IProjectGroupSet',
    ]

from lazr.restful.declarations import (
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_parameters,
    operation_returns_collection_of,
    )
from lazr.restful.fields import (
    CollectionField,
    Reference,
    ReferenceChoice,
    )
from lazr.restful.interface import copy_field
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Bool,
    Datetime,
    Int,
    Object,
    Text,
    TextLine,
    )

from lp import _
from lp.app.interfaces.headings import IRootContext
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    IServiceUsage,
    )
from lp.app.validators.name import name_validator
from lp.blueprints.interfaces.specificationtarget import IHasSpecifications
from lp.blueprints.interfaces.sprint import IHasSprints
from lp.bugs.interfaces.bugtarget import (
    IHasBugs,
    IHasOfficialBugTags,
    )
from lp.bugs.interfaces.bugtracker import IBugTracker
from lp.bugs.interfaces.structuralsubscription import (
    IStructuralSubscriptionTarget,
    )
from lp.code.interfaces.hasbranches import (
    IHasBranches,
    IHasMergeProposals,
    )
from lp.registry.interfaces.announcement import IMakesAnnouncements
from lp.registry.interfaces.karma import IKarmaContext
from lp.registry.interfaces.milestone import (
    ICanGetMilestonesDirectly,
    IHasMilestones,
    IProjectGroupMilestone,
    )
from lp.registry.interfaces.pillar import IPillar
from lp.registry.interfaces.role import (
    IHasAppointedDriver,
    IHasDrivers,
    IHasOwner,
    )
from lp.services.fields import (
    IconImageUpload,
    LogoImageUpload,
    MugshotImageUpload,
    PillarNameField,
    PublicPersonChoice,
    Summary,
    Title,
    URIField,
    )
from lp.translations.interfaces.translationpolicy import ITranslationPolicy


class ProjectNameField(PillarNameField):

    @property
    def _content_iface(self):
        return IProjectGroup


class IProjectGroupModerate(IPillar):
    """IProjectGroup attributes used with launchpad.Moderate permission."""
    reviewed = exported(
        Bool(
            title=_('Reviewed'), required=False,
            description=_("Whether or not this project group has been "
                          "reviewed.")))
    name = exported(
        ProjectNameField(
            title=_('Name'),
            required=True,
            description=_(
                "A unique name, used in URLs, identifying the project "
                "group.  All lowercase, no special characters. "
                "Examples: apache, mozilla, gimp."),
            constraint=name_validator))


class IProjectGroupPublic(
    ICanGetMilestonesDirectly, IHasAppointedDriver, IHasBranches, IHasBugs,
    IHasDrivers, IHasIcon, IHasLogo, IHasMergeProposals, IHasMilestones,
    IHasMugshot, IHasOwner, IHasSpecifications, IHasSprints,
    IMakesAnnouncements, IKarmaContext, IRootContext, IHasOfficialBugTags,
    IServiceUsage):
    """Public IProjectGroup properties."""

    id = Int(title=_('ID'), readonly=True)

    # The following milestone collections are copied from IHasMilestone so that
    # we can override the collection value types to be IProjectGroupMilestone.
    milestones = copy_field(
        IHasMilestones['milestones'],
        value_type=Reference(schema=IProjectGroupMilestone))

    all_milestones = copy_field(
        IHasMilestones['all_milestones'],
        value_type=Reference(schema=IProjectGroupMilestone))

    owner = exported(
        PublicPersonChoice(
            title=_('Maintainer'),
            required=True,
            vocabulary='ValidPillarOwner',
            description=_("The restricted team, moderated team, or person "
                          "who maintains the project group information in "
                          "Launchpad.")))

    registrant = exported(
        PublicPersonChoice(
            title=_('Registrant'),
            required=True,
            readonly=True,
            vocabulary='ValidPersonOrTeam',
            description=_("Project group registrant. Must be a valid "
                          "Launchpad Person.")))

    displayname = exported(
        TextLine(
            title=_('Display Name'),
            description=_(
                "Appropriately capitalised, "
                'and typically ending in "Project". '
                "Examples: the Apache Project, the Mozilla Project, "
                "the Gimp Project.")),
        exported_as="display_name")

    title = exported(
        Title(
            title=_('Title'),
            description=_("The full name of the project group, "
                          "which can contain spaces, special characters, "
                          "etc.")))

    summary = exported(
        Summary(
            title=_('Project Group Summary'),
            description=_(
                "A short paragraph to introduce the project group's work.")))

    description = exported(
        Text(
            title=_('Description'),
            description=_(
                "Details about the project group's work, goals, and "
                "how to contribute. Use plain text, paragraphs are preserved "
                "and URLs are linked in pages. Don't repeat the Summary.")))

    datecreated = exported(
        Datetime(
            title=_('Date Created'),
            description=_(
                "The date this project group was created in Launchpad."),
            readonly=True),
        exported_as="date_created")

    driver = exported(
        PublicPersonChoice(
            title=_("Driver"),
            description=_(
                "This is a project group-wide appointment. Think carefully "
                "here! This person or team will be able to set feature goals "
                "and approve bug targeting and backporting for ANY series in "
                "ANY project in this group. You can also appoint drivers "
                "at the level of a specific project or series. So you may "
                "just want to leave this space blank, and instead let the "
                "individual projects and series have drivers."),
            required=False, vocabulary='ValidPersonOrTeam'))

    homepageurl = exported(
        URIField(
            title=_('Homepage URL'),
            required=False,
            allowed_schemes=['http', 'https', 'ftp'],
            allow_userinfo=False,
            description=_(
                "The project group home page. "
                "Please include the http://")),
        exported_as="homepage_url")

    wikiurl = exported(
        URIField(
            title=_('Wiki URL'),
            required=False,
            allowed_schemes=['http', 'https', 'ftp'],
            allow_userinfo=False,
            description=_("The URL of this project group's wiki, "
                          "if it has one. Please include the http://")),
        exported_as="wiki_url")

    lastdoap = TextLine(
        title=_('Last-parsed RDF fragment'),
        description=_("The last RDF fragment for this "
                      "entity that we received and parsed, or "
                      "generated."),
        required=False)

    sourceforgeproject = exported(
        TextLine(
            title=_("SourceForge Project Name"),
            description=_("The SourceForge project name for this "
                          "project group, if it is in SourceForge."),
            required=False),
        exported_as="sourceforge_project")

    freshmeatproject = exported(
        TextLine(
            title=_("Freshmeat Project Name"),
            description=_("The Freshmeat project name for this "
                          "project group, if it is in Freshmeat."),
            required=False),
        exported_as="freshmeat_project")

    homepage_content = exported(
        Text(
            title=_("Homepage Content"), required=False,
            description=_(
                "The content of this project group's home page. Edit this "
                "and it will be displayed for all the world to see. It is "
                "NOT a wiki so you cannot undo changes.")))

    icon = exported(
        IconImageUpload(
            title=_("Icon"), required=False,
            default_image_resource='/@@/project',
            description=_(
                "A small image of exactly 14x14 pixels and at most 5kb in "
                "size, that can be used to identify this project group. The "
                "icon will be displayed in Launchpad everywhere that we link "
                "to this project group. For example in listings or tables of "
                "active project groups.")))

    logo = exported(
        LogoImageUpload(
            title=_("Logo"), required=False,
            default_image_resource='/@@/project-logo',
            description=_(
                "An image of exactly 64x64 pixels that will be displayed in "
                "the heading of all pages related to this project group. It "
                "should be no bigger than 50kb in size.")))

    mugshot = exported(
        MugshotImageUpload(
            title=_("Brand"), required=False,
            default_image_resource='/@@/project-mugshot',
            description=_(
                "A large image of exactly 192x192 pixels, that will be "
                "displayed on this project group's home page in Launchpad. "
                "It should be no bigger than 100kb in size. ")))

    bugtracker = exported(
        ReferenceChoice(title=_('Bug Tracker'), required=False,
               vocabulary='BugTracker', schema=IBugTracker,
               description=_(
                "The bug tracker the projects in this project group use.")),
        exported_as="bug_tracker")

    # products.value_type will be set to IProduct once IProduct is defined.
    products = exported(
        CollectionField(
            title=_('List of active projects for this project group.'),
            value_type=Reference(Interface)),
        exported_as="projects")

    bug_reporting_guidelines = exported(
        Text(
            title=(
                u"If I\N{right single quotation mark}m reporting a bug, "
                u"I should include, if possible"),
            description=(
                u"These guidelines will be shown to "
                "anyone reporting a bug."),
            required=False,
            max_length=50000))

    bug_reported_acknowledgement = exported(
        Text(
            title=(
                u"After reporting a bug, I can expect the following."),
            description=(
                u"This message of acknowledgement will be displayed "
                "to anyone after reporting a bug."),
            required=False,
            max_length=50000))

    enable_bugfiling_duplicate_search = Bool(
        title=u"Search for possible duplicate bugs when a new bug is filed",
        required=False, readonly=True)

    translatables = Attribute("Products that are translatable in LP")

    def getProduct(name):
        """Get a product with name `name`."""

    def getConfigurableProducts():
        """Get all products that can be edited by user."""

    def has_translatable():
        """Return a boolean showing the existance of translatables products.
        """

    def has_branches():
        """Return a boolean showing the existance of products with branches.
        """

    def hasProducts():
        """Returns True if a project has products associated with it, False
        otherwise.
        """

    def getSeries(series_name):
        """Return a ProjectGroupSeries object with name `series_name`."""

    product_milestones = Attribute('all the milestones for all the products.')


class IProjectGroup(IProjectGroupPublic,
                    IProjectGroupModerate,
                    IStructuralSubscriptionTarget,
                    ITranslationPolicy):
    """A ProjectGroup."""

    export_as_webservice_entry('project_group')


# Interfaces for set

class IProjectGroupSet(Interface):
    """The collection of projects."""

    export_as_webservice_collection(IProjectGroup)

    title = Attribute('Title')

    def __iter__():
        """Return an iterator over all the projects."""

    def __getitem__(name):
        """Get a project by its name."""

    def get(projectid):
        """Get a project by its id.

        If the project can't be found a NotFoundError will be raised.
        """

    def getByName(name, ignore_inactive=False):
        """Return the project with the given name, ignoring inactive projects
        if ignore_inactive is True.

        Return the default value if there is no such project.
        """

    def new(name, displayname, title, homepageurl, summary, description,
            owner, mugshot=None, logo=None, icon=None, registrant=None):
        """Create and return a project with the given arguments.

        For a description of the parameters see `IProjectGroup`.
        """

    def count_all():
        """Return the total number of projects registered in Launchpad."""

    @collection_default_content()
    @operation_parameters(text=TextLine(title=_("Search text")))
    @operation_returns_collection_of(IProjectGroup)
    @export_read_operation()
    def search(text=None, search_products=False):
        """Search through the Registry database for projects that match the
        query terms. text is a piece of text in the title / summary /
        description fields of project (and possibly product). soyuz,
        bazaar, malone etc are hints as to whether the search should
        be limited to projects that are active in those Launchpad
        applications."""

    def forReview():
        """Return a list of ProjectGroups which need review, or which have
        products that needs review."""


class IProjectGroupSeries(IHasSpecifications, IHasAppointedDriver, IHasIcon,
                     IHasOwner):
    """Interface for ProjectGroupSeries.

    This class provides the specifications related to a "virtual project
    series", i.e., to those specifactions that are assigned to a series
    of a product which is part of this project.
    """
    name = TextLine(title=u'The name of the product series.',
                    required=True, readonly=True,
                    constraint=name_validator)

    displayname = TextLine(title=u'Alias for name.',
                           required=True, readonly=True,
                           constraint=name_validator)

    title = TextLine(title=u'The title for this project series.',
                     required=True, readonly=True)

    project = Object(schema=IProjectGroup,
                     title=u"The project this series belongs to",
                     required=True, readonly=True)
