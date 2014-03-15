# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BugAlsoAffectsProductMetaView',
    'BugAlsoAffectsDistroMetaView',
    'BugAlsoAffectsProductWithProductCreationView'
    ]

import cgi
from textwrap import dedent

from lazr.enum import (
    EnumeratedType,
    Item,
    )
from lazr.lifecycle.event import ObjectCreatedEvent
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.event import notify
from zope.formlib import form
from zope.formlib.interfaces import MissingInputError
from zope.formlib.widgets import DropdownWidget
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.browser.multistep import (
    MultiStepView,
    StepView,
    )
from lp.app.enums import ServiceUsage
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.email import email_validator
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.app.widgets.popup import SearchForUpstreamPopupWidget
from lp.app.widgets.textwidgets import StrippedTextWidget
from lp.bugs.browser.widgets.bugtask import (
    BugTaskAlsoAffectsSourcePackageNameWidget,
    )
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    IAddBugTaskForm,
    IAddBugTaskWithProductCreationForm,
    IllegalTarget,
    valid_remote_bug_url,
    )
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import (
    IBugWatchSet,
    NoBugTrackerFound,
    UnrecognizedBugTrackerURL,
    )
from lp.bugs.model.bugtask import (
    validate_new_target,
    validate_target,
    )
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.packaging import (
    IPackagingUtil,
    PackagingType,
    )
from lp.registry.interfaces.product import (
    IProductSet,
    License,
    )
from lp.registry.model.product import Product
from lp.services.fields import StrippedTextLine
from lp.services.propertycache import cachedproperty
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import ILaunchBag


class BugAlsoAffectsProductMetaView(MultiStepView):
    page_title = 'Record as affecting another project'

    @property
    def first_step(self):
        return ChooseProductStep


class BugAlsoAffectsDistroMetaView(MultiStepView):
    page_title = 'Record as affecting another distribution/package'

    @property
    def first_step(self):
        return DistroBugTaskCreationStep


class AlsoAffectsStep(StepView):
    __launchpad_facetname__ = 'bugs'
    schema = IAddBugTaskForm


class LinkPackgingMixin:

    @property
    def can_link_package(self):
        bugtask = self.context
        is_package_bugtask = IDistributionSourcePackage.providedBy(
            bugtask.target)
        return is_package_bugtask and bugtask.target.upstream_product is None


class ChooseProductStep(LinkPackgingMixin, AlsoAffectsStep):
    """View for choosing a product that is affected by a given bug."""

    template = ViewPageTemplateFile(
        '../templates/bugtask-choose-affected-product.pt')

    custom_widget('product', SearchForUpstreamPopupWidget)
    label = u"Record as affecting another project"
    step_name = "choose_product"

    @property
    def _field_names(self):
        """The fields needed to choose an existing project."""
        names = ['product']
        if self.can_link_package:
            names.append('add_packaging')
        return names

    def initialize(self):
        super(ChooseProductStep, self).initialize()
        if (self.widgets['product'].hasInput() or
            not IDistributionSourcePackage.providedBy(self.context.target)):
            return

        self.maybeAddNotificationOrTeleport()

    def maybeAddNotificationOrTeleport(self):
        """If we can't infer the upstream and the target distribution has a
        currentseries we add a notification message telling the user the
        package could be linked to an upstream to avoid this extra step.

        On the other hand, if the upstream can be infered and there's no task
        for it yet, we teleport the user straight to the next step.
        """
        bugtask = self.context
        upstream = bugtask.target.upstream_product
        if upstream is not None:
            try:
                validate_target(bugtask.bug, upstream)
            except IllegalTarget:
                # There is already a task for the upstream.
                pass
            else:
                # We can infer the upstream and there's no bugtask for it,
                # so we can go straight to the page asking for the remote
                # bug URL.
                self.request.form['field.product'] = upstream.name
                self.request.form['field.add_packaging'] = 'off'
                self.next_step = ProductBugTaskCreationStep
            return

    def validateStep(self, data):
        if data.get('product'):
            try:
                validate_new_target(self.context.bug, data.get('product'))
            except IllegalTarget as e:
                self.setFieldError('product', e[0])
            return

        entered_product = self.request.form.get(self.widgets['product'].name)
        if not entered_product:
            return

        # The user has entered a product name but we couldn't find it.
        # Tell the user to search for it using the popup widget as it'll allow
        # the user to register a new product if the one he is looking for is
        # not yet registered.
        widget_link_id = self.widgets['product'].show_widget_id
        self.setFieldError(
            'product',
            structured("""
                There is no project in Launchpad named "%s". Please
                <a href="/projects"
                onclick="LPJS.use('event').Event.simulate(
                         document.getElementById('%s'), 'click');
                         return false;"
                >search for it</a> as it may be
                registered with a different name.""",
                entered_product, widget_link_id))

    def main_action(self, data):
        """Perform the 'Continue' action."""
        # Inject the selected product into the form and set the next_step to
        # be used by our multistep controller.
        self.request.form['field.product'] = data['product'].name
        if data.get('add_packaging', False):
            self.request.form['field.add_packaging'] = 'on'
        else:
            self.request.form['field.add_packaging'] = 'off'
        self.next_step = ProductBugTaskCreationStep


class BugTaskCreationStep(AlsoAffectsStep):
    """The bug task creation step of the AlsoAffects workflow.

    In this view the user specifies the URL for the remote bug and we create
    the new bugtask/bugwatch.

    If the bugtracker in the given URL is not registered in Launchpad, we
    delegate its creation to another view. This other view should then
    delegate the bug task creation to this one once the bugtracker is
    registered.
    """

    custom_widget('bug_url', StrippedTextWidget, displayWidth=62)

    initial_focus_widget = 'bug_url'
    step_name = 'specify_remote_bug_url'
    target_field_names = ()

    # This is necessary so that other views which dispatch work to this one
    # have access to the newly created task.
    task_added = None

    def __init__(self, context, request):
        super(BugTaskCreationStep, self).__init__(context, request)
        self.notifications = []
        self._field_names = ['bug_url'] + list(self.target_field_names)

    def setUpWidgets(self):
        super(BugTaskCreationStep, self).setUpWidgets()
        self.target_widgets = [
            self.widgets[field_name]
            for field_name in self.field_names
            if field_name in self.target_field_names]
        self.bugwatch_widgets = [self.widgets['bug_url']]

    def getTarget(self, data=None):
        """Return the fix target.

        If data is given extract the target from there. Otherwise extract it
        from this view's widgets.
        """
        raise NotImplementedError()

    def main_action(self, data):
        """Create the new bug task.

        If a remote bug URL is given and there's no bug watch registered with
        that URL we create a bug watch and link it to the newly created bug
        task.
        """
        bug_url = data.get('bug_url', '')
        target = self.getTarget(data)

        extracted_bug = None
        extracted_bugtracker = None
        if bug_url:
            try:
                extracted_bugtracker, extracted_bug = getUtility(
                    IBugWatchSet).extractBugTrackerAndBug(bug_url)
            except NoBugTrackerFound:
                # Delegate to another view which will ask the user if (s)he
                # wants to create the bugtracker now.
                if 'product' in self.target_field_names:
                    self.next_step = UpstreamBugTrackerCreationStep
                else:
                    assert 'distribution' in self.target_field_names
                    self.next_step = DistroBugTrackerCreationStep
                return

        if data.get('product') is not None:
            task_target = data['product']
        else:
            task_target = data['distribution']
            if data.get('sourcepackagename') is not None:
                task_target = data['sourcepackagename']
        # The new target has already been validated so don't do it again.
        self.task_added = self.context.bug.addTask(
            getUtility(ILaunchBag).user, task_target, validate_target=False)
        task_added = self.task_added

        if extracted_bug is not None:
            assert extracted_bugtracker is not None, (
                "validate() should have ensured that bugtracker is not None.")
            # Display a notification, if another bug is already linked
            # to the same external bug.
            other_bugs_already_watching = [
                bug for bug in extracted_bugtracker.getBugsWatching(
                    extracted_bug)
                if bug != self.context.bug]
            # Simply add one notification per bug to simplify the
            # implementation; most of the time it will be only one bug.
            for other_bug in other_bugs_already_watching:
                self.request.response.addInfoNotification(
                    structured(
                    '<a href="%(bug_url)s">Bug #%(bug_id)s</a> also links'
                    ' to the added bug watch'
                    ' (%(bugtracker_name)s #%(remote_bug)s).',
                    bug_url=canonical_url(other_bug),
                    bug_id=str(other_bug.id),
                    bugtracker_name=extracted_bugtracker.name,
                    remote_bug=extracted_bug))

            # Make sure that we don't add duplicate bug watches.
            bug_watch = task_added.bug.getBugWatch(
                extracted_bugtracker, extracted_bug)
            if bug_watch is None:
                bug_watch = task_added.bug.addWatch(
                    extracted_bugtracker, extracted_bug, self.user)
            if target.bug_tracking_usage != ServiceUsage.LAUNCHPAD:
                task_added.bugwatch = bug_watch

        if (target.bug_tracking_usage != ServiceUsage.LAUNCHPAD
            and task_added.bugwatch is not None
            and (task_added.bugwatch.bugtracker.bugtrackertype !=
                 BugTrackerType.EMAILADDRESS)):
            # A remote bug task gets its status from a bug watch, so
            # we want its status/importance to be UNKNOWN when
            # created. Status updates cannot be fetched from Email
            # Address bug trackers, and we expect the status and
            # importance to be updated manually, so we do not reset
            # the status and importance here.
            bug_importer = getUtility(ILaunchpadCelebrities).bug_importer
            task_added.transitionToStatus(
                BugTaskStatus.UNKNOWN, bug_importer)
            task_added.transitionToImportance(
                BugTaskImportance.UNKNOWN, bug_importer)

        notify(ObjectCreatedEvent(task_added))
        self.next_url = canonical_url(task_added)


class IAddDistroBugTaskForm(IAddBugTaskForm):

    sourcepackagename = Choice(
        title=_("Source Package Name"), required=False,
        description=_("The source package in which the bug occurs. "
                      "Leave blank if you are not sure."),
        vocabulary='DistributionSourcePackage')


class DistroBugTaskCreationStep(BugTaskCreationStep):
    """Specialized BugTaskCreationStep for reporting a bug in a distribution.
    """

    @property
    def schema(self):
        return IAddBugTaskForm

    custom_widget(
        'sourcepackagename', BugTaskAlsoAffectsSourcePackageNameWidget)

    template = ViewPageTemplateFile('../templates/bugtask-requestfix.pt')

    label = "Also affects distribution/package"
    target_field_names = ('distribution', 'sourcepackagename')

    @property
    def initial_values(self):
        """Return the initial values for the view's fields."""
        return {'distribution': getUtility(ILaunchpadCelebrities).ubuntu}

    def getTarget(self, data=None):
        if data is not None:
            return data.get('distribution')
        else:
            return self.widgets['distribution'].getInputValue()

    def main_action(self, data):
        """Create the new bug task, confirming if necessary."""
        bug_url = data.get('bug_url', '')
        target = self.getTarget(data)

        if (not bug_url and
            not self.request.get('ignore_missing_remote_bug') and
            target.bug_tracking_usage != ServiceUsage.LAUNCHPAD):
            # We have no URL for the remote bug and the target does not use
            # Launchpad for bug tracking, so we warn the user this is not
            # optimal and ask for his confirmation.

            # Add a hidden field to fool LaunchpadFormView into thinking we
            # submitted the action it expected when in fact we're submiting
            # something else to indicate the user has confirmed.
            confirm_button = structured(
                '<input type="hidden" name="%s" value="1" />'
                '<input style="font-size: smaller" type="submit"'
                ' value="Add Anyway" name="ignore_missing_remote_bug" />',
                self.continue_action.__name__)
            self.notifications.append(structured(
                dedent("""
                    %s doesn't use Launchpad as its bug tracker. Without a bug
                    URL to watch, the %s status will not update automatically.
                    %s"""),
                target.displayname, target.displayname,
                confirm_button).escapedtext)
            return None
        # Create the task.
        return super(DistroBugTaskCreationStep, self).main_action(data)

    def validateStep(self, data):
        """Check that

        1. there's no bug_url if the target uses malone;
        2. there is a package with the given name;
        3. it's possible to create a new task for the given package/distro.
        """
        target = self.getTarget(data)
        bug_url = data.get('bug_url')
        if bug_url and target.bug_tracking_usage == ServiceUsage.LAUNCHPAD:
            self.addError(
                "Bug watches can not be added for %s, as it uses Launchpad"
                " as its official bug tracker. Alternatives are to add a"
                " watch for another project, or a comment containing a"
                " URL to the related bug report." % target.displayname)

        distribution = data.get('distribution')
        sourcepackagename = data.get('sourcepackagename')
        entered_package = self.request.form.get(
            self.widgets['sourcepackagename'].name)
        if sourcepackagename is None and entered_package:
            # The entered package doesn't exist.
            if distribution.has_published_binaries:
                binary_tracking = ''
            else:
                binary_tracking = structured(
                    ' Launchpad does not track binary package names '
                    'in %s.', distribution.displayname)
            error = structured(
                'There is no package in %s named "%s".%s',
                distribution.displayname, entered_package,
                binary_tracking)
            self.setFieldError('sourcepackagename', error)
        elif not IDistributionSourcePackage.providedBy(sourcepackagename):
            try:
                target = distribution
                if sourcepackagename:
                    target = target.getSourcePackage(sourcepackagename)
                # The validity of the source package has already been checked
                # by the bug target widget.
                validate_new_target(
                    self.context.bug, target, check_source_package=False)
                if sourcepackagename:
                    data['sourcepackagename'] = target
            except IllegalTarget as e:
                if sourcepackagename:
                    self.setFieldError('sourcepackagename', e[0])
                else:
                    self.setFieldError('distribution', e[0])

        super(DistroBugTaskCreationStep, self).validateStep(data)

    def render(self):
        for bugtask in IBug(self.context).bugtasks:
            if (IDistributionSourcePackage.providedBy(bugtask.target) and
                (not self.widgets['sourcepackagename'].hasInput())):
                self.widgets['sourcepackagename'].setRenderedValue(
                    bugtask.sourcepackagename)
                break
        return super(DistroBugTaskCreationStep, self).render()


class LinkUpstreamHowOptions(EnumeratedType):
    LINK_UPSTREAM = Item(
        """I have the URL for the upstream bug:

        Enter the URL in the upstream bug tracker. If it's in a
        supported upstream bug tracker, Launchpad can download the
        status and display it in the bug report.
        """)

# XXX: GavinPanella 2008-02-13 bug=201793: This will be uncommented in
# a later branch.
#
#     EMAIL_UPSTREAM = Item(
#         """I would like to email an upstream bug contact.
#
#         Launchpad will prepare an example email containing all the
#         pertinent details. You can send it from Launchpad or from your
#         own mail software. If you send it from Launchpad, it'll save
#         the message id and - in the future - will use it to try and
#         follow the resulting conversation, provided it happens on a
#         public mailing list.
#         """)

    EMAIL_UPSTREAM_DONE = Item(
        """I have already emailed an upstream bug contact:

        Launchpad will record that.
        """)

# XXX: GavinPanella 2008-02-13 bug=201793: This additional description
# for EMAIL_UPSTREAM_DONE should be appended when EMAIL_UPSTREAM is
# made available.
#
#   "Next time, try using Launchpad to send the message upstream
#    too. That way it may be able to follow the conversation that
#    results from your bug report. This is especially true for public
#    mailing lists."

    UNLINKED_UPSTREAM = Item(
        """I want to add this upstream project to the bug report, but someone\
        must find or report this bug in the upstream bug tracker.

        Launchpad will record that.
        """)


class IAddBugTaskWithUpstreamLinkForm(IAddBugTaskForm):
    """Form for adding an upstream bugtask with linking options.

    The choices in link_upstream_how correspond to zero or one of the
    text fields. For example, if link_upstream_how is LINK_UPSTREAM
    then bug_url is the relevant field, and the other text fields,
    like upstream_email_address_done, can be ignored.

    That also explains why none of the text fields are required. That
    check is left to the view, in part so that better error messages
    can be provided.
    """
    # link_upstream_how must have required=False, since
    # ProductBugTaskCreationStep doesn't always display a form input for it.
    link_upstream_how = Choice(
        title=_('How'), required=False,
        vocabulary=LinkUpstreamHowOptions,
        default=LinkUpstreamHowOptions.LINK_UPSTREAM,
        description=_("How to link to an upstream bug."))
    bug_url = StrippedTextLine(
        title=_('Bug URL'), required=False, constraint=valid_remote_bug_url,
        description=_("The URL of this bug in the remote bug tracker."))
    upstream_email_address_done = StrippedTextLine(
        title=_('Email Address'), required=False, constraint=email_validator,
        description=_("The upstream email address that this bug has been "
                      "forwarded to."))


class ProductBugTaskCreationStep(BugTaskCreationStep):
    """Specialized BugTaskCreationStep for reporting a bug in an upstream."""

    template = ViewPageTemplateFile(
        '../templates/bugtask-requestfix-upstream.pt')

    label = "Confirm project"
    target_field_names = ('product', 'add_packaging')
    main_action_label = u'Add to Bug Report'
    schema = IAddBugTaskWithUpstreamLinkForm

    custom_widget('link_upstream_how', LaunchpadRadioWidget,
                  _displayItemForMissingValue=False)
    custom_widget('bug_url', StrippedTextWidget, displayWidth=42)
    custom_widget('upstream_email_address_done',
                  StrippedTextWidget, displayWidth=42)

    @property
    def field_names(self):
        return ['link_upstream_how', 'upstream_email_address_done'] + (
            super(ProductBugTaskCreationStep, self).field_names)

    def validate_widgets(self, data, names=None):
        # The form is essentially just a radio group, with zero or one
        # related text widgets per choice. The text widget should be
        # validated when its corresponding radio button has been
        # selected, otherwise we should do no validation because we
        # don't want to issue errors for widgets that we and the user
        # are not interested in.

        # Collect all the widget names.
        if names is None:
            names = set()
        else:
            names = set(names)
        names.update(widget.context.__name__ for widget in self.widgets)

        # A mapping from radio buttons to their related text widgets.
        link_upstream_options = {
            LinkUpstreamHowOptions.LINK_UPSTREAM:
                'bug_url',
            LinkUpstreamHowOptions.EMAIL_UPSTREAM_DONE:
                'upstream_email_address_done'}

        # Examine the radio group if it has valid input.
        link_upstream_how = self.widgets['link_upstream_how']
        if link_upstream_how.hasValidInput():
            link_upstream_how = link_upstream_how.getInputValue()

            # Don't request validation for text widgets that are not
            # related to the current radio selection.
            for option, name in link_upstream_options.iteritems():
                if link_upstream_how != option:
                    names.discard(name)
                elif self.widgets[name].hasValidInput():
                    # Check that input has been provided because the
                    # fields in the schema are set to required=False
                    # to make the radio+text-widget mechanism work.
                    if not self.widgets[name].getInputValue():
                        self.setFieldError(
                            name, 'Required input is missing.')

        else:
            # Don't validate these widgets when we don't yet know how
            # we intend to link upstream.
            names.difference_update(link_upstream_options.itervalues())

        return super(ProductBugTaskCreationStep,
                     self).validate_widgets(data, names)

    def getTarget(self, data=None):
        if data is not None:
            return data.get('product')
        else:
            return self.widgets['product'].getInputValue()

    @cachedproperty
    def link_upstream_how_items(self):
        """Manually create and pick apart a radio widget.

        On its own, `LaunchpadRadioWidget` does not render quite how
        we need it, because we're interspersing related text
        widgets. We need to dig down a bit and place the individually
        rendered radio buttons into our custom layout.
        """
        widget = self.widgets['link_upstream_how']
        try:
            current_value = widget.getInputValue()
        except MissingInputError:
            current_value = LinkUpstreamHowOptions.LINK_UPSTREAM
        items = widget.renderItems(current_value)

        # The items list is returned in the same order as the
        # widget.vocabulary enumerator. It is important that
        # link_upstream_how has _displayItemForMissingValue=False
        # so that renderItems() doesn't return an extra radio button which
        # prevents it from matching widget.vocabulary's ordering.
        return dict((entry.token, items[i])
                    for i, entry in enumerate(widget.vocabulary))

    def main_action(self, data):
        link_upstream_how = data.get('link_upstream_how')

        if link_upstream_how == LinkUpstreamHowOptions.UNLINKED_UPSTREAM:
            # Erase bug_url because we don't want to create a bug
            # watch against a specific URL.
            if 'bug_url' in data:
                del data['bug_url']
        elif link_upstream_how == LinkUpstreamHowOptions.EMAIL_UPSTREAM_DONE:
            # Ensure there's a bug tracker for this email address.
            bug_url = 'mailto:' + data['upstream_email_address_done']
            getUtility(IBugTrackerSet).ensureBugTracker(
                bug_url, self.user, BugTrackerType.EMAILADDRESS)
            data['bug_url'] = bug_url
        if data.get('add_packaging', False):
            # Create a packaging link so that Launchpad will suggest the
            # upstream project to the user.
            series = self.context.target.distribution.currentseries
            if series:
                getUtility(IPackagingUtil).createPackaging(
                    productseries=data['product'].development_focus,
                    sourcepackagename=self.context.target.sourcepackagename,
                    distroseries=series, packaging=PackagingType.PRIME,
                    owner=self.user)
        return super(ProductBugTaskCreationStep, self).main_action(data)

    @property
    def upstream_bugtracker_links(self):
        """Return the upstream bugtracker links for the current target.

        :return: The bug tracker links for the target, as returned by
            BugTracker.getBugFilingAndSearchLinks(). If product.bugtracker
            is None, return None.
        """
        target = self.getTarget()

        if not target.bugtracker:
            return None

        bug = self.context.bug
        title = bug.title
        description = u"Originally reported at:\n  %s\n\n%s" % (
            canonical_url(bug), bug.description)
        return target.bugtracker.getBugFilingAndSearchLinks(
            target.remote_product, title, description)


class BugTrackerCreationStep(AlsoAffectsStep):
    """View for creating a bugtracker from the given URL.

    This view will ask the user if he really wants to register the new bug
    tracker, perform the registration and then delegate to one of
    BugTaskCreationStep's subclasses.
    """

    custom_widget('bug_url', StrippedTextWidget, displayWidth=62)
    step_name = "bugtracker_creation"
    main_action_label = u'Register Bug Tracker and Add to Bug Report'
    _next_step = None

    def main_action(self, data):
        assert self._next_step is not None, (
            "_next_step must be specified in subclasses.")
        bug_url = data.get('bug_url').strip()
        try:
            getUtility(IBugWatchSet).extractBugTrackerAndBug(bug_url)
        except NoBugTrackerFound as error:
            getUtility(IBugTrackerSet).ensureBugTracker(
                error.base_url, self.user, error.bugtracker_type)
        self.next_step = self._next_step


class DistroBugTrackerCreationStep(BugTrackerCreationStep):

    _next_step = DistroBugTaskCreationStep
    _field_names = ['distribution', 'sourcepackagename', 'bug_url']
    custom_widget('distribution', DropdownWidget, visible=False)
    custom_widget('sourcepackagename', DropdownWidget, visible=False)
    label = "Also affects distribution/package"
    template = ViewPageTemplateFile(
        '../templates/bugtask-confirm-bugtracker-creation.pt')


class UpstreamBugTrackerCreationStep(BugTrackerCreationStep):

    schema = IAddBugTaskWithUpstreamLinkForm
    _next_step = ProductBugTaskCreationStep
    _field_names = ['product', 'bug_url', 'link_upstream_how']
    custom_widget('product', DropdownWidget, visible=False)
    custom_widget('link_upstream_how',
                  LaunchpadRadioWidget, visible=False)
    label = "Confirm project"
    template = ViewPageTemplateFile(
        '../templates/bugtask-confirm-bugtracker-creation.pt')


class BugAlsoAffectsProductWithProductCreationView(LinkPackgingMixin,
                                                   LaunchpadFormView):
    """Register a product and indicate this bug affects it.

    If there's no bugtracker with the given URL registered in Launchpad, then
    a new bugtracker is created as well.
    """

    label = "Register project affected by this bug"
    schema = IAddBugTaskWithProductCreationForm
    custom_widget('bug_url', StrippedTextWidget, displayWidth=62)
    custom_widget('existing_product', LaunchpadRadioWidget)
    existing_products = None
    MAX_PRODUCTS_TO_DISPLAY = 10
    licenses = [License.DONT_KNOW]

    @property
    def field_names(self):
        """The fields needed to choose an existing project."""
        names = ['bug_url', 'displayname', 'name', 'summary']
        if self.can_link_package:
            names.append('add_packaging')
        return names

    def _loadProductsUsingBugTracker(self):
        """Find products using the bugtracker wich runs on the given URL.

        These products are stored in self.existing_products.

        If there are too many products using that bugtracker then we'll store
        only the first ones that somehow match the name given.
        """
        bug_url = self.request.form.get('field.bug_url')
        if not bug_url:
            return

        bugwatch_set = getUtility(IBugWatchSet)
        try:
            bugtracker, bug = bugwatch_set.extractBugTrackerAndBug(bug_url)
        except (NoBugTrackerFound, UnrecognizedBugTrackerURL):
            # There's no bugtracker registered with the given URL, so we
            # don't need to worry about finding products using it.
            return

        count = bugtracker.products.count()
        if count > 0 and count <= self.MAX_PRODUCTS_TO_DISPLAY:
            self.existing_products = list(bugtracker.products)
        elif count > self.MAX_PRODUCTS_TO_DISPLAY:
            # Use a local import as we don't want removeSecurityProxy used
            # anywhere else.
            from zope.security.proxy import removeSecurityProxy
            name_matches = removeSecurityProxy(
                getUtility(IProductSet).search(self.user,
                self.request.form.get('field.name')))
            products = name_matches.find(Product.bugtracker == bugtracker.id)
            self.existing_products = list(
                products[:self.MAX_PRODUCTS_TO_DISPLAY])
        else:
            # The bugtracker is registered in Launchpad but there are no
            # products using it at the moment.
            pass

    def setUpFields(self):
        """Setup an extra field with all products using the given bugtracker.

        This extra field is setup only if there is one or more products using
        that bugtracker.
        """
        super(
            BugAlsoAffectsProductWithProductCreationView, self).setUpFields()
        self._loadProductsUsingBugTracker()
        if self.existing_products is None or len(self.existing_products) < 1:
            # No need to setup any extra fields.
            return

        terms = []
        for product in self.existing_products:
            terms.append(SimpleTerm(product, product.name, product.title))
        existing_product = form.FormField(
            Choice(__name__='existing_product',
                   title=_("Existing project"), required=True,
                   vocabulary=SimpleVocabulary(terms)))
        self.form_fields += form.Fields(existing_product)
        if 'field.existing_product' not in self.request.form:
            # This is the first time the form is being submitted, so the
            # request doesn't contain a value for the existing_product
            # widget and thus we'll end up rendering an error message around
            # said widget unless we sneak a value for it in our request.
            self.request.form['field.existing_product'] = terms[0].token

    def validate_existing_product(self, action, data):
        """Check if the chosen project is not already affected by this bug."""
        self._validate(action, data)
        project = data.get('existing_product')
        try:
            validate_target(self.context.bug, project)
        except IllegalTarget as e:
            self.setFieldError('existing_product', e[0])

    @action('Use Existing Project', name='use_existing_product',
            validator=validate_existing_product)
    def use_existing_product_action(self, action, data):
        """Record the chosen project as being affected by this bug.

        Also creates a bugwatch for the given remote bug.
        """
        data['product'] = data['existing_product']
        self._createBugTaskAndWatch(data)

    @action('Continue', name='continue')
    def continue_action(self, action, data):
        """Create a new product and a bugtask for this bug on that product.

        If the URL of the remote bug given is of a bugtracker used by any
        other products registered in Launchpad, then we show these products to
        the user and ask if he doesn't want to create the task in one of them.
        """
        if self.existing_products and not self.request.form.get('create_new'):
            # Present the projects using that bugtracker to the user as
            # possible options to report the bug on. If there are too many
            # projects using that bugtracker then show only the ones that
            # match the text entered as the project's name
            return
        # Products created through this view have DONT_KNOW licensing.
        product = getUtility(IProductSet).createProduct(
            owner=self.user,
            name=data['name'],
            displayname=data['displayname'], title=data['displayname'],
            summary=data['summary'], licenses=self.licenses,
            registrant=self.user)
        data['product'] = product
        self._createBugTaskAndWatch(data, set_bugtracker=True)
        # Now that the product is configured set the owner to be the registry
        # experts team.
        product.owner = getUtility(ILaunchpadCelebrities).registry_experts

    def _createBugTaskAndWatch(self, data, set_bugtracker=False):
        """Create a bugtask and bugwatch on the chosen product.

        If set_bugtracker is True then the bugtracker of the newly created
        watch is set as the product's bugtracker.

        This is done by manually calling the main_action() method of
        UpstreamBugTrackerCreationStep and ProductBugTaskCreationStep.

        This method also sets self.next_url to the URL of the newly added
        bugtask.
        """
        # XXX: Guilherme Salgado, 2007-11-20: This relies on the fact that
        # these actions work using only the form data and the context.
        # (They don't require any side-effects done  during initialize().)
        # They should probably be extracted outside of the view to
        # make that explicit.
        view = UpstreamBugTrackerCreationStep(self.context, self.request)
        view.main_action(data)

        view = ProductBugTaskCreationStep(self.context, self.request)
        view.main_action(data)

        if set_bugtracker:
            data['product'].bugtracker = view.task_added.bugwatch.bugtracker
        self.next_url = canonical_url(view.task_added)
