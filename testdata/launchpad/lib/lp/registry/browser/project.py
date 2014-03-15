# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Project-related View Classes"""

__metaclass__ = type

__all__ = [
    'ProjectActionMenu',
    'ProjectAddProductView',
    'ProjectAddQuestionView',
    'ProjectAddView',
    'ProjectAnswersMenu',
    'ProjectBrandingView',
    'ProjectBugsMenu',
    'ProjectEditView',
    'ProjectFacets',
    'ProjectMaintainerReassignmentView',
    'ProjectNavigation',
    'ProjectOverviewMenu',
    'ProjectRdfView',
    'ProjectReviewView',
    'ProjectSeriesSpecificationsMenu',
    'ProjectSetBreadcrumb',
    'ProjectSetContextMenu',
    'ProjectSetNavigation',
    'ProjectSetNavigationMenu',
    'ProjectSetView',
    'ProjectSpecificationsMenu',
    'ProjectView',
    ]


from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.event import notify
from zope.formlib import form
from zope.formlib.widgets import TextWidget
from zope.interface import (
    implements,
    Interface,
    )
from zope.lifecycleevent import ObjectCreatedEvent
from zope.schema import Choice

from lp import _
from lp.answers.browser.question import QuestionAddView
from lp.answers.browser.questiontarget import (
    QuestionCollectionAnswersMenu,
    QuestionTargetFacetMixin,
    )
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.browser.lazrjs import InlinePersonEditPickerWidget
from lp.app.browser.tales import format_link
from lp.app.errors import NotFoundError
from lp.blueprints.browser.specificationtarget import (
    HasSpecificationsMenuMixin,
    )
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    StructuralSubscriptionMenuMixin,
    StructuralSubscriptionTargetTraversalMixin,
    )
from lp.registry.browser import (
    add_subscribe_link,
    BaseRdfView,
    )
from lp.registry.browser.announcement import HasAnnouncementsView
from lp.registry.browser.branding import BrandingChangeView
from lp.registry.browser.menu import (
    IRegistryCollectionNavigationMenu,
    RegistryCollectionActionMenuBase,
    )
from lp.registry.browser.objectreassignment import ObjectReassignmentView
from lp.registry.browser.pillar import PillarViewMixin
from lp.registry.browser.product import (
    ProductAddView,
    ProjectAddStepOne,
    ProjectAddStepTwo,
    )
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.projectgroup import (
    IProjectGroup,
    IProjectGroupSeries,
    IProjectGroupSet,
    )
from lp.registry.model.milestonetag import (
    ProjectGroupMilestoneTag,
    validate_tags,
    )
from lp.services.feeds.browser import FeedsMixin
from lp.services.fields import (
    PillarAliases,
    PublicPersonChoice,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    ApplicationMenu,
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    LaunchpadView,
    Link,
    Navigation,
    StandardLaunchpadFacets,
    stepthrough,
    structured,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.menu import NavigationMenu


class ProjectNavigation(Navigation,
    StructuralSubscriptionTargetTraversalMixin):

    usedfor = IProjectGroup

    def traverse(self, name):
        return self.context.getProduct(name)

    @stepthrough('+milestone')
    def traverse_milestone(self, name):
        return self.context.getMilestone(name)

    @stepthrough('+announcement')
    def traverse_announcement(self, name):
        return self.context.getAnnouncement(name)

    @stepthrough('+series')
    def traverse_series(self, series_name):
        return self.context.getSeries(series_name)

    @stepthrough('+tags')
    def traverse_tags(self, name):
        tags = name.split(u',')
        if validate_tags(tags):
            return ProjectGroupMilestoneTag(self.context, tags)


class ProjectSetNavigation(Navigation):

    usedfor = IProjectGroupSet

    def traverse(self, name):
        # Raise a 404 on an invalid project name
        project = self.context.getByName(name)
        if project is None:
            raise NotFoundError(name)
        return self.redirectSubTree(canonical_url(project))


class ProjectSetBreadcrumb(Breadcrumb):
    """Builds a breadcrumb for an `IProjectGroupSet`."""
    text = 'Project Groups'


class ProjectSetContextMenu(ContextMenu):

    usedfor = IProjectGroupSet
    links = ['register', 'listall']

    @enabled_with_permission('launchpad.Moderate')
    def register(self):
        text = 'Register a project group'
        return Link('+new', text, icon='add')

    def listall(self):
        text = 'List all project groups'
        return Link('+all', text, icon='list')


class ProjectFacets(QuestionTargetFacetMixin, StandardLaunchpadFacets):
    """The links that will appear in the facet menu for an IProjectGroup."""

    usedfor = IProjectGroup

    enable_only = ['overview', 'branches', 'bugs', 'specifications',
                   'answers', 'translations']

    @cachedproperty
    def has_products(self):
        return self.context.hasProducts()

    def branches(self):
        text = 'Code'
        return Link('', text, enabled=self.has_products)

    def bugs(self):
        site = 'bugs'
        text = 'Bugs'
        return Link('', text, enabled=self.has_products, site=site)

    def answers(self):
        site = 'answers'
        text = 'Answers'
        return Link('', text, enabled=self.has_products, site=site)

    def specifications(self):
        site = 'blueprints'
        text = 'Blueprints'
        return Link('', text, enabled=self.has_products, site=site)

    def translations(self):
        site = 'translations'
        text = 'Translations'
        return Link('', text, enabled=self.has_products, site=site)


class ProjectAdminMenuMixin:

    @enabled_with_permission('launchpad.Moderate')
    def administer(self):
        text = 'Administer'
        return Link('+review', text, icon='edit')


class ProjectEditMenuMixin(ProjectAdminMenuMixin):

    @enabled_with_permission('launchpad.Edit')
    def branding(self):
        text = 'Change branding'
        return Link('+branding', text, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def reassign(self):
        text = 'Change maintainer'
        summary = 'Change the maintainer of this project group'
        return Link('+reassign', text, summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def driver(self):
        text = 'Appoint driver'
        summary = 'Appoint the driver of this project group'
        return Link('+driver', text, summary, icon='edit')


class ProjectOverviewMenu(ProjectEditMenuMixin, ApplicationMenu):

    usedfor = IProjectGroup
    facet = 'overview'
    links = [
        'branding', 'driver', 'reassign', 'top_contributors', 'announce',
        'announcements', 'rdf', 'new_product', 'administer', 'milestones']

    @enabled_with_permission('launchpad.Edit')
    def new_product(self):
        text = 'Register a project in %s' % self.context.displayname
        return Link('+newproduct', text, icon='add')

    def top_contributors(self):
        text = 'More contributors'
        return Link('+topcontributors', text, icon='info')

    @enabled_with_permission('launchpad.Edit')
    def announce(self):
        text = 'Make announcement'
        summary = 'Publish an item of news for this project'
        return Link('+announce', text, summary, icon='add')

    def announcements(self):
        text = 'Read all announcements'
        enabled = bool(self.context.getAnnouncements())
        return Link('+announcements', text, icon='info', enabled=enabled)

    def milestones(self):
        text = 'See all milestones'
        return Link('+milestones', text, icon='info')

    def rdf(self):
        text = structured(
            'Download <abbr title="Resource Description Framework">'
            'RDF</abbr> metadata')
        return Link('+rdf', text, icon='download-icon')


class IProjectGroupActionMenu(Interface):
    """Marker interface for views that use ProjectActionMenu."""


class ProjectActionMenu(ProjectAdminMenuMixin,
                        StructuralSubscriptionMenuMixin,
                        NavigationMenu):

    usedfor = IProjectGroupActionMenu
    facet = 'overview'
    title = 'Action menu'

    @cachedproperty
    def links(self):
        links = []
        add_subscribe_link(links)
        links.extend(['edit', 'administer'])
        return links

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change details'
        return Link('+edit', text, icon='edit')


class IProjectGroupEditMenu(Interface):
    """A marker interface for the 'Change details' navigation menu."""


class ProjectEditNavigationMenu(NavigationMenu, ProjectEditMenuMixin):
    """A sub-menu for different aspects of editing a Project's details."""

    usedfor = IProjectGroupEditMenu
    facet = 'overview'
    title = 'Change project group'
    links = ('branding', 'reassign', 'driver', 'administer')


class ProjectSpecificationsMenu(NavigationMenu,
                                HasSpecificationsMenuMixin):
    usedfor = IProjectGroup
    facet = 'specifications'
    links = ['listall', 'doc', 'assignments', 'new', 'register_sprint']


class ProjectAnswersMenu(QuestionCollectionAnswersMenu):
    """Menu for the answers facet of projects."""

    usedfor = IProjectGroup
    facet = 'answers'
    links = QuestionCollectionAnswersMenu.links + ['new']

    def new(self):
        text = 'Ask a question'
        return Link('+addquestion', text, icon='add')


class ProjectBugsMenu(StructuralSubscriptionMenuMixin,
                      ApplicationMenu):

    usedfor = IProjectGroup
    facet = 'bugs'

    @cachedproperty
    def links(self):
        links = ['new']
        add_subscribe_link(links)
        return links

    def new(self):
        text = 'Report a Bug'
        return Link('+filebug', text, icon='add')


class ProjectView(PillarViewMixin, HasAnnouncementsView, FeedsMixin):

    implements(IProjectGroupActionMenu)

    @property
    def maintainer_widget(self):
        return InlinePersonEditPickerWidget(
            self.context, IProjectGroup['owner'],
            format_link(self.context.owner, empty_value="Not yet selected"),
            header='Change maintainer', edit_view='+reassign',
            step_title='Select a new maintainer',
            null_display_value="Not yet selected", show_create_team=True)

    @property
    def driver_widget(self):
        return InlinePersonEditPickerWidget(
            self.context, IProjectGroup['driver'],
            format_link(self.context.driver, empty_value="Not yet selected"),
            header='Change driver', edit_view='+driver',
            step_title='Select a new driver',
            null_display_value="Not yet selected",
            help_link="/+help-registry/driver.html", show_create_team=True)

    def initialize(self):
        super(ProjectView, self).initialize()
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user)

    @property
    def page_title(self):
        return '%s in Launchpad' % self.context.displayname

    @cachedproperty
    def has_many_projects(self):
        """Does the projectgroup have many sub projects.

        The number of sub projects can break the preferred layout so the
        template may want to plan for a long list.
        """
        return len(self.context.products) > 10

    @property
    def project_group_milestone_tag(self):
        """Return a ProjectGroupMilestoneTag based on this project."""
        return ProjectGroupMilestoneTag(self.context, [])


class ProjectEditView(LaunchpadEditFormView):
    """View class that lets you edit a Project object."""
    implements(IProjectGroupEditMenu)
    label = "Change project group details"
    page_title = label
    schema = IProjectGroup
    field_names = [
        'displayname', 'title', 'summary', 'description',
        'bug_reporting_guidelines', 'bug_reported_acknowledgement',
        'homepageurl', 'bugtracker', 'sourceforgeproject',
        'freshmeatproject', 'wikiurl']

    @action('Change Details', name='change')
    def edit(self, action, data):
        self.updateContextFromData(data)

    @property
    def next_url(self):
        if self.context.active:
            return canonical_url(self.context)
        else:
            # If the project is inactive, we can't traverse to it
            # anymore.
            return canonical_url(getUtility(IProjectGroupSet))


class ProjectReviewView(ProjectEditView):

    label = "Review upstream project group details"
    default_field_names = ['name', 'owner', 'active', 'reviewed']

    def setUpFields(self):
        """Setup the normal fields from the schema plus adds 'Registrant'.

        The registrant is normally a read-only field and thus does not have a
        proper widget created by default.  Even though it is read-only, admins
        need the ability to change it.
        """
        self.field_names = self.default_field_names[:]
        admin = check_permission('launchpad.Admin', self.context)
        if not admin:
            self.field_names.remove('owner')
        moderator = check_permission('launchpad.Moderate', self.context)
        if not moderator:
            self.field_names.remove('name')
        super(ProjectReviewView, self).setUpFields()
        self.form_fields = self._createAliasesField() + self.form_fields
        if admin:
            self.form_fields = (
                self.form_fields + self._createRegistrantField())

    def _createAliasesField(self):
        """Return a PillarAliases field for IProjectGroup.aliases."""
        return form.Fields(
            PillarAliases(
                __name__='aliases', title=_('Aliases'),
                description=_('Other names (separated by space) under which '
                              'this project group is known.'),
                required=False, readonly=False),
            render_context=self.render_context)

    def _createRegistrantField(self):
        """Return a popup widget person selector for the registrant.

        This custom field is necessary because *normally* the registrant is
        read-only but we want the admins to have the ability to correct legacy
        data that was set before the registrant field existed.
        """
        return form.Fields(
            PublicPersonChoice(
                __name__='registrant',
                title=_('Project Registrant'),
                description=_('The person who originally registered the '
                              'project group.  Distinct from the current '
                              'owner.  This is historical data and should '
                              'not be changed without good cause.'),
                vocabulary='ValidPersonOrTeam',
                required=True,
                readonly=False,
                ),
            render_context=self.render_context
            )


class ProjectGroupAddStepOne(ProjectAddStepOne):
    """project/+newproduct view class for creating a new project.

    The new project will automatically be a part of the project group.
    """
    page_title = "Register a project in your project group"

    @cachedproperty
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Register a project in Launchpad as a part of %s' % (
            self.context.displayname)

    @property
    def _next_step(self):
        """See `ProjectAddStepOne`."""
        return ProjectGroupAddStepTwo


class ProjectGroupAddStepTwo(ProjectAddStepTwo):
    """Step 2 (of 2) in the +newproduct project add wizard."""

    page_title = "Register a project in your project group"

    def create_product(self, data):
        """Create the product from the user data."""
        return getUtility(IProductSet).createProduct(
            owner=self.user,
            name=data['name'],
            title=data['title'],
            summary=data['summary'],
            displayname=data['displayname'],
            licenses=data['licenses'],
            license_info=data['license_info'],
            information_type=data.get('information_type'),
            project=self.context,
            )

    @property
    def label(self):
        """See `LaunchpadFormView`."""
        return 'Register %s (%s) in Launchpad as a part of %s' % (
            self.request.form['displayname'], self.request.form['name'],
            self.context.displayname)


class ProjectAddProductView(ProductAddView):
    """The controlling view for project/+newproduct."""

    @property
    def first_step(self):
        """See `MultiStepView`."""
        return ProjectGroupAddStepOne


class ProjectSetNavigationMenu(RegistryCollectionActionMenuBase):
    """Action menu for project group index."""
    usedfor = IProjectGroupSet
    links = [
        'register_team',
        'register_project',
        'create_account',
        'register_project_group',
        'view_all_project_groups',
        ]

    @enabled_with_permission('launchpad.Moderate')
    def register_project_group(self):
        text = 'Register a project group'
        return Link('+new', text, icon='add')

    def view_all_project_groups(self):
        text = 'View all project groups'
        return Link('+all', text, icon='list')


class ProjectSetView(LaunchpadView):
    """View for project group index page."""

    implements(IRegistryCollectionNavigationMenu)

    page_title = "Project groups registered in Launchpad"

    def __init__(self, context, request):
        super(ProjectSetView, self).__init__(context, request)
        self.form = self.request.form_ng
        self.search_string = self.form.getOne('text', None)
        self.search_requested = False
        if (self.search_string is not None):
            self.search_requested = True
        self.results = None

    @cachedproperty
    def search_results(self):
        """Use searchtext to find the list of Projects that match
        and then present those as a list. Only do this the first
        time the method is called, otherwise return previous results.
        """
        self.results = self.context.search(
            text=self.search_string,
            search_products=True)
        return self.results

    @property
    def matches(self):
        """Number of matches."""
        if self.results is None:
            return 0
        else:
            return self.results.count()


class ProjectAddView(LaunchpadFormView):

    schema = IProjectGroup
    field_names = [
        'name',
        'displayname',
        'title',
        'summary',
        'description',
        'owner',
        'homepageurl',
        ]
    custom_widget('homepageurl', TextWidget, displayWidth=30)
    label = _('Register a project group with Launchpad')
    page_title = label
    project = None

    @action(_('Add'), name='add')
    def add_action(self, action, data):
        """Create the new Project from the form details."""
        self.project = getUtility(IProjectGroupSet).new(
            name=data['name'].lower().strip(),
            displayname=data['displayname'],
            title=data['title'],
            homepageurl=data['homepageurl'],
            summary=data['summary'],
            description=data['description'],
            owner=data['owner'],
            )
        notify(ObjectCreatedEvent(self.project))

    @property
    def next_url(self):
        assert self.project is not None, 'No project has been created'
        return canonical_url(self.project)


class ProjectBrandingView(BrandingChangeView):

    schema = IProjectGroup
    field_names = ['icon', 'logo', 'mugshot']


class ProjectRdfView(BaseRdfView):
    """A view that sets its mime-type to application/rdf+xml"""

    template = ViewPageTemplateFile(
        '../templates/project-rdf.pt')

    @property
    def filename(self):
        return '%s-project' % self.context.name


class ProjectAddQuestionView(QuestionAddView):
    """View used to create a question from an IProjectGroup context."""

    search_field_names = ['product'] + QuestionAddView.search_field_names

    def setUpFields(self):
        # Add a 'product' field to the beginning of the form.
        QuestionAddView.setUpFields(self)
        self.form_fields = self.createProductField() + self.form_fields

    def setUpWidgets(self):
        fields = self._getFieldsForWidgets()
        # We need to initialize the widget in two phases because
        # the language vocabulary factory will try to access the product
        # widget to find the final context.
        self.widgets = form.setUpWidgets(
            fields.select('product'),
            self.prefix, self.context, self.request,
            data=self.initial_values, ignore_request=False)
        self.widgets += form.setUpWidgets(
            fields.omit('product'),
            self.prefix, self.context, self.request,
            data=self.initial_values, ignore_request=False)

    def createProductField(self):
        """Create a Choice field to select one of the project's products."""
        return form.Fields(
            Choice(
                __name__='product', vocabulary='ProjectProducts',
                title=_('Project'),
                description=_(
                    '${context} is a group of projects, which specific '
                    'project do you have a question about?',
                    mapping=dict(context=self.context.title)),
                required=True),
            render_context=self.render_context)

    @property
    def page_title(self):
        """The current page title."""
        return _('Ask a question about a project in ${project}',
                 mapping=dict(project=self.context.displayname))

    @property
    def question_target(self):
        """The IQuestionTarget to use is the selected product."""
        if self.widgets['product'].hasValidInput():
            return self.widgets['product'].getInputValue()
        else:
            return None


class ProjectSeriesSpecificationsMenu(ApplicationMenu):

    usedfor = IProjectGroupSeries
    facet = 'specifications'
    links = ['listall', 'doc', 'assignments']

    def listall(self):
        text = 'List all blueprints'
        return Link('+specs?show=all', text, icon='info')

    def doc(self):
        text = 'List documentation'
        summary = 'Show all completed informational specifications'
        return Link('+documentation', text, summary, icon="info")

    def assignments(self):
        text = 'Assignments'
        return Link('+assignments', text, icon='info')


class ProjectMaintainerReassignmentView(ObjectReassignmentView):
    """View class for changing project maintainer."""
    ownerOrMaintainerName = 'maintainer'
