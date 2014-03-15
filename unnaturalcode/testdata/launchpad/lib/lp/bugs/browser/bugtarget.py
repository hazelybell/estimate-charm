# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IBugTarget-related browser views."""

__metaclass__ = type

__all__ = [
    "BugsVHostBreadcrumb",
    "BugsPatchesView",
    "BugTargetBugListingView",
    "BugTargetBugTagsView",
    "FileBugAdvancedView",
    "FileBugGuidedView",
    "FileBugViewBase",
    "IProductBugConfiguration",
    "OfficialBugTagsManageView",
    "ProductConfigureBugTrackerView",
    "ProjectGroupFileBugGuidedView",
    "product_to_productbugconfiguration",
    ]

from cStringIO import StringIO
from datetime import datetime
from functools import partial
import httplib
from operator import itemgetter
import urllib
from urlparse import urljoin

from lazr.restful.interface import copy_field
from lazr.restful.interfaces import IJSONRequestCache
from pytz import timezone
from simplejson import dumps
from sqlobject import SQLObjectNotFound
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.formlib.form import Fields
from zope.formlib.interfaces import InputErrors
from zope.formlib.widgets import TextWidget
from zope.interface import (
    alsoProvides,
    implements,
    Interface,
    )
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.schema import Choice
from zope.schema.interfaces import TooLong
from zope.schema.vocabulary import SimpleVocabulary
from zope.security.proxy import removeSecurityProxy

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    safe_action,
    )
from lp.app.browser.lazrjs import vocabulary_to_choice_edit_items
from lp.app.browser.stringformatter import FormattersAPI
from lp.app.enums import (
    InformationType,
    PRIVATE_INFORMATION_TYPES,
    PUBLIC_INFORMATION_TYPES,
    SECURITY_INFORMATION_TYPES,
    ServiceUsage,
    )
from lp.app.errors import (
    NotFoundError,
    UnexpectedFormData,
    )
from lp.app.interfaces.launchpad import (
    ILaunchpadCelebrities,
    ILaunchpadUsage,
    )
from lp.app.utilities import json_dump_information_types
from lp.app.validators.name import valid_name_pattern
from lp.app.vocabularies import InformationTypeVocabulary
from lp.app.widgets.itemswidgets import LaunchpadRadioWidgetWithDescription
from lp.app.widgets.product import (
    GhostCheckBoxWidget,
    GhostWidget,
    ProductBugTrackerWidget,
    )
from lp.bugs.browser.structuralsubscription import (
    expose_structural_subscription_data_to_js,
    )
from lp.bugs.browser.widgets.bug import (
    BugTagsWidget,
    LargeBugTagsWidget,
    )
from lp.bugs.interfaces.apportjob import IProcessApportBlobJobSource
from lp.bugs.interfaces.bug import (
    CreateBugParams,
    IBug,
    IBugAddForm,
    IBugSet,
    IProjectGroupBugAddForm,
    )
from lp.bugs.interfaces.bugsupervisor import IHasBugSupervisor
from lp.bugs.interfaces.bugtarget import (
    IBugTarget,
    IOfficialBugTagTargetPublic,
    IOfficialBugTagTargetRestricted,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    IBugTaskSet,
    UNRESOLVED_BUGTASK_STATUSES,
    )
from lp.bugs.interfaces.bugtracker import IBugTracker
from lp.bugs.model.bugtask import BugTask
from lp.bugs.model.structuralsubscription import (
    get_structural_subscriptions_for_target,
    )
from lp.bugs.publisher import BugsLayer
from lp.bugs.utilities.filebugdataparser import FileBugData
from lp.hardwaredb.interfaces.hwdb import IHWSubmissionSet
from lp.registry.browser.product import ProductConfigureBase
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.registry.vocabularies import ValidPersonOrTeamVocabulary
from lp.services.config import config
from lp.services.job.interfaces.job import JobStatus
from lp.services.librarian.browser import ProxiedLibraryFileAlias
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    urlappend,
    )
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.breadcrumb import Breadcrumb
from lp.services.webapp.escaping import structured

# A simple vocabulary for the subscribe_to_existing_bug form field.
SUBSCRIBE_TO_BUG_VOCABULARY = SimpleVocabulary.fromItems(
    [('yes', True), ('no', False)])


class IProductBugConfiguration(Interface):
    """A composite schema for editing bug app configuration."""

    bug_supervisor = copy_field(
        IHasBugSupervisor['bug_supervisor'], readonly=False)
    official_malone = copy_field(ILaunchpadUsage['official_malone'])
    enable_bug_expiration = copy_field(
        ILaunchpadUsage['enable_bug_expiration'])
    bugtracker = copy_field(IProduct['bugtracker'])
    remote_product = copy_field(IProduct['remote_product'])
    bug_reporting_guidelines = copy_field(
        IBugTarget['bug_reporting_guidelines'])
    bug_reported_acknowledgement = copy_field(
        IBugTarget['bug_reported_acknowledgement'])
    enable_bugfiling_duplicate_search = copy_field(
        IBugTarget['enable_bugfiling_duplicate_search'])


def product_to_productbugconfiguration(product):
    """Adapts an `IProduct` into an `IProductBugConfiguration`."""
    alsoProvides(
        removeSecurityProxy(product), IProductBugConfiguration)
    return product


class ProductConfigureBugTrackerView(ProductConfigureBase):
    """View class to configure the bug tracker for a project."""

    label = "Configure bug tracker"
    schema = IProductBugConfiguration
    # This ProductBugTrackerWidget renders enable_bug_expiration and
    # remote_product as subordinate fields, so this view suppresses them.
    custom_widget('bugtracker', ProductBugTrackerWidget)
    custom_widget('enable_bug_expiration', GhostCheckBoxWidget)
    custom_widget('remote_product', GhostWidget)

    @property
    def field_names(self):
        """Return the list of field names to display."""
        field_names = [
            "bugtracker",
            "enable_bug_expiration",
            "remote_product",
            "bug_reporting_guidelines",
            "bug_reported_acknowledgement",
            "enable_bugfiling_duplicate_search",
            ]
        if check_permission("launchpad.Edit", self.context):
            field_names.append("bug_supervisor")

        return field_names

    def validate(self, data):
        """Constrain bug expiration to Launchpad Bugs tracker."""
        super(ProductConfigureBugTrackerView, self).validate(data)
        # enable_bug_expiration is disabled by JavaScript when bugtracker
        # is not 'In Launchpad'. The constraint is enforced here in case the
        # JavaScript fails to activate or run. Note that the bugtracker
        # name : values are {'In Launchpad' : object, 'Somewhere else' : None
        # 'In a registered bug tracker' : IBugTracker}.
        bugtracker = data.get('bugtracker', None)
        if bugtracker is None or IBugTracker.providedBy(bugtracker):
            data['enable_bug_expiration'] = False

    @action("Change", name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)


class FileBugViewBase(LaunchpadFormView):
    """Base class for views related to filing a bug."""

    implements(IBrowserPublisher)

    schema = IBug

    custom_widget('information_type', LaunchpadRadioWidgetWithDescription)

    extra_data_token = None

    def __init__(self, context, request):
        super(FileBugViewBase, self).__init__(context, request)
        self.extra_data = FileBugData()

    def initialize(self):
        # redirect_ubuntu_filebug is a cached_property.
        # Access it first just to compute its value. Because it
        # makes a DB access to get the bug supervisor, it causes
        # trouble in tests when form validation errors occur. Because the
        # transaction is doomed, the storm cache is invalidated and accessing
        # the property will result in a a LostObjectError, because
        # the created objects disappeared. Not likely a problem in production
        # since the objects will still be in the DB, but doesn't hurt there
        # either. It makes for better diagnosis of failing tests.
        if self.redirect_ubuntu_filebug:
            pass

        # The JSON cache must be populated before the super call, since
        # the form is rendered during LaunchpadFormView's initialize()
        # when an action is invokved.
        cache = IJSONRequestCache(self.request)
        cache.objects['bug_private_by_default'] = (
            self.context.pillar.getDefaultBugInformationType() in
            PRIVATE_INFORMATION_TYPES)
        json_dump_information_types(
            cache, self.context.pillar.getAllowedBugInformationTypes())

        bugtask_status_data = vocabulary_to_choice_edit_items(
            BugTaskStatus, include_description=True, css_class_prefix='status',
            excluded_items=[
                BugTaskStatus.UNKNOWN,
                BugTaskStatus.EXPIRED,
                BugTaskStatus.INVALID,
                BugTaskStatus.OPINION,
                BugTaskStatus.WONTFIX,
                BugTaskStatus.INCOMPLETE])
        cache.objects['bugtask_status_data'] = bugtask_status_data
        bugtask_importance_data = vocabulary_to_choice_edit_items(
            BugTaskImportance, include_description=True,
            css_class_prefix='importance',
            excluded_items=[BugTaskImportance.UNKNOWN])
        cache.objects['bugtask_importance_data'] = bugtask_importance_data
        cache.objects['enable_bugfiling_duplicate_search'] = (
            self.context.enable_bugfiling_duplicate_search)

        super(FileBugViewBase, self).initialize()

        if (self.extra_data_token is not None and
            not self.extra_data_to_process):
            # self.extra_data has been initialized in publishTraverse().
            if self.extra_data.initial_summary:
                self.widgets['title'].setRenderedValue(
                    self.extra_data.initial_summary)
            if self.extra_data.initial_tags:
                self.widgets['tags'].setRenderedValue(
                    self.extra_data.initial_tags)
            # XXX: Bjorn Tillenius 2006-01-15:
            #      We should include more details of what will be added
            #      to the bug report.
            self.request.response.addNotification(
                'Extra debug information will be added to the bug report'
                ' automatically.')

    @cachedproperty
    def redirect_ubuntu_filebug(self):
        if IDistribution.providedBy(self.context):
            bug_supervisor = self.context.bug_supervisor
        elif (IDistributionSourcePackage.providedBy(self.context) or
              ISourcePackage.providedBy(self.context)):
            bug_supervisor = self.context.distribution.bug_supervisor
        else:
            bug_supervisor = None

        # Work out whether the redirect should be overidden.
        do_not_redirect = (
            self.request.form.get('no-redirect') is not None or
            [key for key in self.request.form.keys()
            if 'field.actions' in key] != [] or
            self.user.inTeam(bug_supervisor))

        return (
            config.malone.ubuntu_disable_filebug and
            self.targetIsUbuntu() and
            self.extra_data_token is None and
            not do_not_redirect)

    @property
    def field_names(self):
        """Return the list of field names to display."""
        context = self.context
        field_names = ['title', 'comment', 'tags']
        if self.is_bug_supervisor:
            field_names.append('information_type')
        else:
            field_names.append('security_related')
        field_names.extend([
            'bug_already_reported_as', 'filecontent', 'patch',
            'attachment_description', 'subscribe_to_existing_bug'])
        if (IDistribution.providedBy(context) or
            IDistributionSourcePackage.providedBy(context)):
            field_names.append('packagename')

        if self.is_bug_supervisor:
            field_names.extend(
                ['assignee', 'importance', 'milestone', 'status'])

        return field_names

    @property
    def default_information_type(self):
        value = self.context.pillar.getDefaultBugInformationType()
        if (self.extra_data
            and self.extra_data.private
            and value in PUBLIC_INFORMATION_TYPES):
            value = InformationType.USERDATA
        return value

    @property
    def initial_values(self):
        """Give packagename a default value, if applicable."""
        values = {'information_type': self.default_information_type}

        if IDistributionSourcePackage.providedBy(self.context):
            values['packagename'] = self.context.name

        return values

    def contextIsProduct(self):
        return IProduct.providedBy(self.context)

    def contextIsProject(self):
        return False

    def targetIsUbuntu(self):
        ubuntu = getUtility(ILaunchpadCelebrities).ubuntu
        return self.context == ubuntu

    def getPackageNameFieldCSSClass(self):
        """Return the CSS class for the packagename field."""
        if self.widget_errors.get("packagename"):
            return 'error'
        else:
            return ''

    def validate(self, data):
        """Make sure the package name, if provided, exists in the distro."""
        # The comment field is only required if filing a new bug.
        if self.submit_bug_action.submitted():
            comment = data.get('comment')
            # The widget only exposes the error message. The private
            # attr contains the real error.
            widget_error = self.widgets.get('comment')._error
            if widget_error and isinstance(widget_error.errors, TooLong):
                self.setFieldError('comment',
                    'The description is too long. If you have lots of '
                    'text to add, attach a file to the bug instead.')
            elif not comment or widget_error is not None:
                self.setFieldError(
                    'comment', "Provide details about the issue.")
            # Check if there is an extra description, and if it is too long.
            if self.extra_data.extra_description:
                if len("%s\n\n%s" % (
                    comment, self.extra_data.extra_description)) > 50000:
                    self.setFieldError(
                        'comment', 'The description and the additional '
                        'information is too long. If you have lots of text '
                        'to add, attach a file to the bug instead.')
        # Check a bug has been selected when the user wants to
        # subscribe to an existing bug.
        elif self.this_is_my_bug_action.submitted():
            if not data.get('bug_already_reported_as'):
                self.setFieldError('bug_already_reported_as',
                                   "Please choose a bug.")
        else:
            # We only care about those two actions.
            pass

        # We have to poke at the packagename value directly in the
        # request, because if validation failed while getting the
        # widget's data, it won't appear in the data dict.
        form = self.request.form
        if form.get("packagename_option") == "choose":
            packagename = form.get("field.packagename")
            if packagename:
                if IDistribution.providedBy(self.context):
                    distribution = self.context
                else:
                    assert IDistributionSourcePackage.providedBy(self.context)
                    distribution = self.context.distribution

                try:
                    distribution.guessPublishedSourcePackageName(packagename)
                except NotFoundError:
                    if distribution.series:
                        # If a distribution doesn't have any series,
                        # it won't have any source packages published at
                        # all, so we set the error only if there are
                        # series.
                        packagename_error = (
                            '"%s" does not exist in %s. Please choose a '
                            "different package. If you're unsure, please "
                            'select "I don\'t know"' % (
                                packagename, distribution.displayname))
                        self.setFieldError("packagename", packagename_error)
            else:
                self.setFieldError("packagename",
                                   "Please enter a package name")

    def setUpWidgets(self):
        """Customize the onKeyPress event of the package name chooser."""
        super(FileBugViewBase, self).setUpWidgets()

        if "packagename" in self.field_names:
            self.widgets["packagename"].onKeyPress = (
                "selectWidget('choose', event)")

    def setUpFields(self):
        """Set up the form fields. See `LaunchpadFormView`."""
        super(FileBugViewBase, self).setUpFields()

        if self.is_bug_supervisor:
            info_type_vocab = InformationTypeVocabulary(
                types=self.context.pillar.getAllowedBugInformationTypes())
            information_type_field = copy_field(
                IBug['information_type'], readonly=False,
                vocabulary=info_type_vocab)
            self.form_fields = self.form_fields.omit('information_type')
            self.form_fields += Fields(information_type_field)
        else:
            security_related_field = copy_field(
                IBug['security_related'], readonly=False)
            self.form_fields = self.form_fields.omit('security_related')
            self.form_fields += Fields(security_related_field)

        # Override the vocabulary for the subscribe_to_existing_bug
        # field.
        subscribe_field = Choice(
            __name__='subscribe_to_existing_bug',
            title=u'Subscribe to this bug',
            vocabulary=SUBSCRIBE_TO_BUG_VOCABULARY,
            required=True, default=False)

        self.form_fields = self.form_fields.omit('subscribe_to_existing_bug')
        self.form_fields += Fields(subscribe_field)

    def contextUsesMalone(self):
        """Does the context use Malone as its official bugtracker?"""
        bug_tracking_usage = self.getMainContext().bug_tracking_usage
        return bug_tracking_usage == ServiceUsage.LAUNCHPAD

    def contextAllowsNewBugs(self):
        return (self.contextUsesMalone() and
                self.getMainContext().getAllowedBugInformationTypes())

    def shouldSelectPackageName(self):
        """Should the radio button to select a package be selected?"""
        return (
            self.request.form.get("field.packagename") or
            self.initial_values.get("packagename"))

    def handleSubmitBugFailure(self, action, data, errors):
        return self.showFileBugForm()

    @action("Submit Bug Report", name="submit_bug",
            failure=handleSubmitBugFailure)
    def submit_bug_action(self, action, data):
        """Add a bug to this IBugTarget."""
        title = data["title"]
        comment = data["comment"].rstrip()
        packagename = data.get("packagename")

        information_type = data.get("information_type")
        if information_type is None:
            # If the old UI is enabled, security bugs are always embargoed
            # when filed, but can be disclosed after they've been reported.
            # Otherwise we use the default.
            if data.get("security_related"):
                information_type = InformationType.PRIVATESECURITY
            else:
                information_type = self.default_information_type

        context = self.context

        # Ensure that no package information is used, if the user
        # enters a package name but then selects "I don't know".
        if self.request.form.get("packagename_option") == "none":
            packagename = None

        linkified_ack = structured(FormattersAPI(
            self.getAcknowledgementMessage(self.context)).text_to_html(
                last_paragraph_class="last"))
        notifications = [linkified_ack]
        params = CreateBugParams(
            title=title, comment=comment, owner=self.user,
            information_type=information_type,
            tags=data.get('tags'))
        if IDistribution.providedBy(context) and packagename:
            # We don't know if the package name we got was a source or binary
            # package name, so let the Soyuz API figure it out for us.
            packagename = str(packagename.name)
            try:
                sourcepackagename = context.guessPublishedSourcePackageName(
                    packagename)
            except NotFoundError:
                notifications.append(
                    "The package %s is not published in %s; the "
                    "bug was targeted only to the distribution."
                    % (packagename, context.displayname))
                params.comment += (
                    "\r\n\r\nNote: the original reporter indicated "
                    "the bug was in package %r; however, that package "
                    "was not published in %s." % (
                        packagename, context.displayname))
            else:
                context = context.getSourcePackage(sourcepackagename.name)

        extra_data = self.extra_data
        if extra_data.extra_description:
            params.comment = "%s\n\n%s" % (
                params.comment, extra_data.extra_description)
            notifications.append(
                'Additional information was added to the bug description.')

        # Apply any extra options given by privileged users.
        if self.is_bug_supervisor:
            if 'assignee' in data:
                params.assignee = data['assignee']
            if 'status' in data:
                params.status = data['status']
            if 'importance' in data:
                params.importance = data['importance']
            if 'milestone' in data:
                params.milestone = data['milestone']

        self.added_bug = bug = context.createBug(params)

        for comment in extra_data.comments:
            bug.newMessage(self.user, bug.followup_subject(), comment)
            notifications.append(
                'A comment with additional information was added to the'
                ' bug report.')

        # XXX 2007-01-19 gmb:
        #     We need to have a proper FileUpload widget rather than
        #     this rather hackish solution.
        attachment = self.request.form.get(self.widgets['filecontent'].name)
        if attachment or extra_data.attachments:
            # Attach all the comments to a single empty comment.
            attachment_comment = bug.newMessage(
                owner=self.user, subject=bug.followup_subject(), content=None,
                send_notifications=False)

            # Deal with attachments added in the filebug form.
            if attachment:
                # We convert slashes in filenames to hyphens to avoid
                # problems.
                filename = attachment.filename.replace('/', '-')

                # If the user hasn't entered a description for the
                # attachment we use its name.
                file_description = None
                if 'attachment_description' in data:
                    file_description = data['attachment_description']
                if file_description is None:
                    file_description = filename

                bug.addAttachment(
                    owner=self.user, data=StringIO(data['filecontent']),
                    filename=filename, description=file_description,
                    comment=attachment_comment, is_patch=data['patch'])

                notifications.append(
                    'The file "%s" was attached to the bug report.'
                    % filename)

            for attachment in extra_data.attachments:
                bug.linkAttachment(
                    owner=self.user, file_alias=attachment['file_alias'],
                    description=attachment['description'],
                    comment=attachment_comment,
                    send_notifications=False)
                notifications.append(
                    'The file "%s" was attached to the bug report.'
                    % attachment['file_alias'].filename)

        if extra_data.subscribers:
            # Subscribe additional subscribers to this bug
            for subscriber in extra_data.subscribers:
                valid_person_vocabulary = ValidPersonOrTeamVocabulary()
                try:
                    person = valid_person_vocabulary.getTermByToken(
                        subscriber).value
                except LookupError:
                    # We cannot currently pass this error up to the user, so
                    # we'll just ignore it.
                    pass
                else:
                    bug.subscribe(person, self.user)
                    notifications.append(
                        '%s has been subscribed to this bug.' %
                        person.displayname)

        submission_set = getUtility(IHWSubmissionSet)
        for submission_key in extra_data.hwdb_submission_keys:
            submission = submission_set.getBySubmissionKey(
                submission_key, self.user)
            if submission is not None:
                bug.linkHWSubmission(submission)

        # Give the user some feedback on the bug just opened.
        for notification in notifications:
            self.request.response.addNotification(notification)
        if bug.information_type in SECURITY_INFORMATION_TYPES:
            self.request.response.addNotification(
                structured(
                'Security-related bugs are by default private '
                '(visible only to their direct subscribers). '
                'You may choose to <a href="+secrecy">publicly '
                'disclose</a> this bug.'))
        elif bug.information_type in PRIVATE_INFORMATION_TYPES:
            self.request.response.addNotification(
                structured(
                'This bug report has been marked private '
                '(visible only to its direct subscribers). '
                'You may choose to <a href="+secrecy">change this</a>.'))

        self.request.response.redirect(canonical_url(bug.bugtasks[0]))

    @action("Yes, this is the bug I'm trying to report",
            name="this_is_my_bug", failure=handleSubmitBugFailure)
    def this_is_my_bug_action(self, action, data):
        """Subscribe to the bug suggested."""
        bug = data.get('bug_already_reported_as')
        subscribe = data.get('subscribe_to_existing_bug')

        if bug.isUserAffected(self.user):
            self.request.response.addNotification(
                "This bug is already marked as affecting you.")
        else:
            bug.markUserAffected(self.user)
            self.request.response.addNotification(
                "This bug has been marked as affecting you.")

        # If the user wants to be subscribed, subscribe them, unless
        # they're already subscribed.
        if subscribe:
            if bug.isSubscribed(self.user):
                self.request.response.addNotification(
                    "You are already subscribed to this bug.")
            else:
                bug.subscribe(self.user, self.user)
                self.request.response.addNotification(
                    "You have subscribed to this bug report.")

        self.next_url = canonical_url(bug.bugtasks[0])

    def showFileBugForm(self):
        """Override this method in base classes to show the filebug form."""
        raise NotImplementedError

    @property
    def inline_filebug_base_url(self):
        """Return the base URL for the current request.

        This allows us to build URLs in Javascript without guessing at
        domains.
        """
        return self.request.getRootURL(None)

    @property
    def inline_filebug_form_url(self):
        """Return the URL to the inline filebug form.

        If a token was passed to this view, it will be passed through
        to the inline bug filing form via the returned URL.
        """
        url = canonical_url(self.context, view_name='+filebug-inline-form')
        if self.extra_data_token is not None:
            url = urlappend(url, self.extra_data_token)
        return url

    @property
    def duplicate_search_url(self):
        """Return the URL to the inline duplicate search view."""
        url = canonical_url(self.context, view_name='+filebug-show-similar')
        if self.extra_data_token is not None:
            url = urlappend(url, self.extra_data_token)
        return url

    def publishTraverse(self, request, name):
        """See IBrowserPublisher."""
        if self.extra_data_token is not None:
            # publishTraverse() has already been called once before,
            # which means that he URL contains more path components than
            # expected.
            raise NotFound(self, name, request=request)

        self.extra_data_token = name
        if self.extra_data_processing_job is None:
            # The URL might be mistyped, or the blob has expired.
            # XXX: Bjorn Tillenius 2006-01-15:
            #      We should handle this case better, since a user might
            #      come to this page when finishing his account
            #      registration. In that case we should inform the user
            #      that the blob has expired.
            raise NotFound(self, name, request=request)
        else:
            self.extra_data = self.extra_data_processing_job.getFileBugData()

        return self

    def browserDefault(self, request):
        """See IBrowserPublisher."""
        return self, ()

    def getProductOrDistroFromContext(self):
        """Return the product or distribution relative to the context."""
        return self.context.pillar

    def showOptionalMarker(self, field_name):
        """See `LaunchpadFormView`."""
        # The comment field _is_ required, but only when filing the
        # bug. Since the same form is also used for subscribing to a
        # bug, the comment field in the schema cannot be marked
        # required=True. Instead it's validated in
        # FileBugViewBase.validate. So... we need to suppress the
        # "(Optional)" marker.
        if field_name == 'comment':
            return False
        else:
            return LaunchpadFormView.showOptionalMarker(self, field_name)

    def getRelevantBugTask(self, bug):
        """Return the first bugtask from this bug that's relevant in the
        current context.

        This is a pragmatic function, not general purpose. It tries to
        find a bugtask that can be used to pretty-up the page, making
        it more user-friendly and informative. It's not concerned by
        total accuracy, and will return the first 'relevant' bugtask
        it finds even if there are other candidates. Be warned!
        """
        for bugtask in bug.bugtasks:
            if self.context in (bugtask.target, bugtask.pillar):
                return bugtask
        return None

    default_bug_reported_acknowledgement = "Thank you for your bug report."

    def getAcknowledgementMessage(self, context):
        """An acknowlegement message displayed to the user."""
        # If a given context doesnot have a custom message, we go up in the
        # "object hierachy" until we find one. If no cusotmized messages
        # exist for any conext, a default message is returned.
        #
        # bug_reported_acknowledgement is defined as a "real" property
        # for IDistribution, IDistributionSourcePackage, IProduct and
        # IProjectGroup. Other IBugTarget implementations inherit this
        # property from their parents. For these classes, we can directly
        # try to find a custom message farther up in the hierarchy.
        message = context.bug_reported_acknowledgement
        if message is not None and len(message.strip()) > 0:
            return message
        next_context = None
        if IProductSeries.providedBy(context):
            # we don't need to look at
            # context.product.bug_reported_acknowledgement because a
            # product series inherits this property from the product.
            next_context = context.product.project
        elif IProduct.providedBy(context):
            next_context = context.project
        elif IDistributionSourcePackage.providedBy(context):
            next_context = context.distribution
        # IDistroseries and ISourcePackage inherit
        # bug_reported_acknowledgement from their IDistribution, so we
        # don't need to look up this property in IDistribution.
        # IDistribution and IProjectGroup don't have any parents.
        elif (IDistribution.providedBy(context) or
              IProjectGroup.providedBy(context) or
              IDistroSeries.providedBy(context) or
              ISourcePackage.providedBy(context)):
            pass
        else:
            raise TypeError("Unexpected bug target: %r" % context)
        if next_context is not None:
            return self.getAcknowledgementMessage(next_context)
        return self.default_bug_reported_acknowledgement

    @cachedproperty
    def extra_data_processing_job(self):
        """Return the ProcessApportBlobJob for a given BLOB token."""
        if self.extra_data_token is None:
            # If there's no extra data token, don't bother looking for a
            # ProcessApportBlobJob.
            return None

        try:
            return getUtility(IProcessApportBlobJobSource).getByBlobUUID(
                self.extra_data_token)
        except SQLObjectNotFound:
            return None

    @property
    def extra_data_to_process(self):
        """Return True if there is extra data to process."""
        apport_processing_job = self.extra_data_processing_job
        if apport_processing_job is None:
            return False
        elif apport_processing_job.job.status == JobStatus.COMPLETED:
            return False
        else:
            return True

    @property
    def bug_reporting_guidelines(self):
        """Guidelines for filing bugs in the current context.

        Returns a list of dicts, with each dict containing values for
        "preamble" and "content".
        """
        guidelines = []
        content = self.context.bug_reporting_guidelines
        if content is not None and len(content) > 0:
            guidelines.append({
                "source": self.context.bugtargetdisplayname,
                "content": content,
                })
        # Distribution source packages are shown with both their
        # own reporting guidelines and those of their
        # distribution.
        if IDistributionSourcePackage.providedBy(self.context):
            distribution = self.context.distribution
            content = distribution.bug_reporting_guidelines
            if content is not None and len(content) > 0:
                guidelines.append({
                    "source": distribution.bugtargetdisplayname,
                    "content": content,
                    })
        return guidelines

    def getMainContext(self):
        if IDistributionSourcePackage.providedBy(self.context):
            return self.context.distribution
        else:
            return self.context

    @cachedproperty
    def is_bug_supervisor(self):
        """ Return True if the logged in user is a bug supervisor."""
        context = self.getMainContext()
        return BugTask.userHasBugSupervisorPrivilegesContext(
            context, self.user)


class FileBugAdvancedView(LaunchpadView):
    """Browser view for filing a bug.

    This view exists only to redirect from +filebug-advanced to +filebug.
    """

    def initialize(self):
        filebug_url = canonical_url(
            self.context, rootsite='bugs', view_name='+filebug')
        self.request.response.redirect(
            filebug_url, status=httplib.MOVED_PERMANENTLY)


class FilebugShowSimilarBugsView(FileBugViewBase):
    """A view for showing possible dupes for a bug.

    This view will only be used to populate asynchronously-driven parts
    of a page.
    """
    schema = IBugAddForm

    # XXX: Brad Bollenbach 2006-10-04: This assignment to actions is a
    # hack to make the action decorator Just Work across inheritance.
    actions = FileBugViewBase.actions
    custom_widget('title', TextWidget, displayWidth=40)
    custom_widget('tags', BugTagsWidget)

    _MATCHING_BUGS_LIMIT = 10
    show_summary_in_results = False

    @property
    def action_url(self):
        """Return the +filebug page as the action URL.

        This enables better validation error handling,
        since the form is always used inline on the +filebug page.
        """
        url = '%s/+filebug' % canonical_url(self.context)
        if self.extra_data_token is not None:
            url = urlappend(url, self.extra_data_token)
        return url

    @property
    def search_text(self):
        """Return the search string entered by the user."""
        return self.request.get('title')

    @cachedproperty
    def similar_bugs(self):
        """Return the similar bugs based on the user search."""
        title = self.search_text
        if not title:
            return []
        elif IProduct.providedBy(self.context):
            context_params = {'product': self.context}
        elif IDistribution.providedBy(self.context):
            context_params = {'distribution': self.context}
        else:
            assert IDistributionSourcePackage.providedBy(self.context), (
                    'Unknown search context: %r' % self.context)
            context_params = {
                'distribution': self.context.distribution,
                'sourcepackagename': self.context.sourcepackagename}

        matching_bugtasks = getUtility(IBugTaskSet).findSimilar(
            self.user, title, **context_params)
        matching_bugs = getUtility(IBugSet).getDistinctBugsForBugTasks(
            matching_bugtasks, self.user, self._MATCHING_BUGS_LIMIT)
        return matching_bugs

    @property
    def show_duplicate_list(self):
        """Return whether or not to show the duplicate list.

        We only show the dupes if:
          - The context uses Malone AND
          - There are dupes to show AND
          - There are no widget errors.
        """
        return (
            self.contextUsesMalone() and
            len(self.similar_bugs) > 0 and
            len(self.widget_errors) == 0)


class FileBugGuidedView(FilebugShowSimilarBugsView):

    _SEARCH_FOR_DUPES = ViewPageTemplateFile(
        "../templates/bugtarget-filebug-search.pt")
    _PROJECTGROUP_SEARCH_FOR_DUPES = ViewPageTemplateFile(
        "../templates/projectgroup-filebug-search.pt")
    _FILEBUG_FORM = ViewPageTemplateFile(
        "../templates/bugtarget-filebug-submit-bug.pt")

    # XXX 2009-07-17 Graham Binns
    #     As above, this assignment to actions is to make sure that the
    #     actions from the ancestor views are preserved, otherwise they
    #     get nuked.
    actions = FilebugShowSimilarBugsView.actions
    template = _SEARCH_FOR_DUPES

    focused_element_id = 'field.title'
    show_summary_in_results = True

    def initialize(self):
        super(FileBugGuidedView, self).initialize()
        if self.redirect_ubuntu_filebug:
            # The user is trying to file a new Ubuntu bug via the web
            # interface and without using apport. Redirect to a page
            # explaining the preferred bug-filing procedure.
            self.request.response.redirect(
                config.malone.ubuntu_bug_filing_url)

    @property
    def page_title(self):
        return 'Report a bug about %s' % self.context.title

    @safe_action
    @action("Continue", name="search")
    def search_action(self, action, data):
        """Search for similar bug reports."""
        # Don't give focus to any widget, to ensure that the browser
        # won't scroll past the "possible duplicates" list.
        self.initial_focus_widget = None
        return self.showFileBugForm()

    @property
    def search_text(self):
        """Return the search string entered by the user."""
        try:
            return self.widgets['title'].getInputValue()
        except InputErrors:
            return None

    def validate_no_dupe_found(self, action, data):
        return ()

    @action("Continue", name="continue",
            validator="validate_no_dupe_found")
    def continue_action(self, action, data):
        """The same action as no-dupe-found, with a different label."""
        return self.showFileBugForm()

    def showFileBugForm(self):
        return self._FILEBUG_FORM()


class ProjectGroupFileBugGuidedView(LaunchpadFormView):
    """Guided filebug pages for IProjectGroup."""

    schema = IProjectGroupBugAddForm

    custom_widget('title', TextWidget, displayWidth=40)
    custom_widget('tags', BugTagsWidget)

    extra_data_to_process = False

    @property
    def field_names(self):
        return ['product', 'title', 'tags']

    @property
    def page_title(self):
        return 'Report a bug about %s' % self.context.title

    @cachedproperty
    def products_using_malone(self):
        return [
            product for product in self.context.products
            if product.bug_tracking_usage == ServiceUsage.LAUNCHPAD]

    @property
    def default_product(self):
        if len(self.products_using_malone) > 0:
            return self.products_using_malone[0]
        else:
            return None

    def contextUsesMalone(self):
        return self.default_product is not None

    def contextAllowsNewBugs(self):
        return True

    def contextIsProduct(self):
        return False

    def contextIsProject(self):
        return True

    def getProductOrDistroFromContext(self):
        return None

    @safe_action
    @action("Continue", name="projectgroupsearch")
    def projectgroup_search_action(self, action, data):
        """Redirect to the chosen product's form."""
        base = canonical_url(
            data['product'], view_name='+filebug', rootsite='bugs')
        title = data['title'].encode('utf8')
        query = urllib.urlencode([
            ('field.title', title),
            ('field.tags', ' '.join(data['tags'])),
            ])
        url = '%s?%s' % (base, query)
        self.request.response.redirect(url)


class BugTargetBugListingView(LaunchpadView):
    """Helper methods for rendering bug listings."""

    @property
    def series_list(self):
        if IDistroSeries(self.context, None):
            series = self.context.distribution.series
        elif IDistribution(self.context, None):
            series = self.context.series
        elif IProductSeries(self.context, None):
            series = self.context.product.series
        elif IProduct(self.context, None):
            series = self.context.series
        else:
            raise AssertionError("series_list called with illegal context")
        return list(series)

    @property
    def milestones_list(self):
        if IDistroSeries(self.context, None):
            milestone_resultset = self.context.distribution.milestones
        elif IDistribution(self.context, None):
            milestone_resultset = self.context.milestones
        elif IProductSeries(self.context, None):
            milestone_resultset = self.context.product.milestones
        elif IProduct(self.context, None):
            milestone_resultset = self.context.milestones
        else:
            raise AssertionError(
                "milestones_list called with illegal context")
        return list(milestone_resultset)

    @property
    def series_buglistings(self):
        """Return a buglisting for each series.

        The list is sorted newest series to oldest.

        The count only considers bugs that the user would actually be
        able to see in a listing.
        """
        # Circular fail.
        from lp.bugs.model.bugsummary import BugSummary
        series_buglistings = []
        bug_task_set = getUtility(IBugTaskSet)
        series_list = self.series_list
        if not series_list:
            return series_buglistings
        # This would be better as delegation not a case statement.
        if IDistroSeries(self.context, None):
            backlink = BugSummary.distroseries_id
        elif IDistribution(self.context, None):
            backlink = BugSummary.distroseries_id
        elif IProductSeries(self.context, None):
            backlink = BugSummary.productseries_id
        elif IProduct(self.context, None):
            backlink = BugSummary.productseries_id
        else:
            raise AssertionError("illegal context %r" % self.context)
        counts = bug_task_set.countBugs(self.user, series_list, (backlink,))
        for series in series_list:
            series_bug_count = counts.get((series.id,), 0)
            if series_bug_count > 0:
                series_buglistings.append(
                    dict(
                        title=series.name,
                        url=canonical_url(series) + "/+bugs",
                        count=series_bug_count,
                        ))
        return series_buglistings

    @property
    def milestone_buglistings(self):
        """Return a buglisting for each milestone."""
        # Circular fail.
        from lp.bugs.model.bugsummary import (
            BugSummary,
            CombineBugSummaryConstraint,
            )
        milestone_buglistings = []
        bug_task_set = getUtility(IBugTaskSet)
        milestones = self.milestones_list
        if not milestones:
            return milestone_buglistings
        # Note: this isn't totally optimal as a query, but its the simplest to
        # code; we can iterate if needed to provide one complex context to
        # countBugs.
        query_milestones = map(partial(
            CombineBugSummaryConstraint, self.context), milestones)
        counts = bug_task_set.countBugs(
            self.user, query_milestones, (BugSummary.milestone_id,))
        for milestone in milestones:
            milestone_bug_count = counts.get((milestone.id,), 0)
            if milestone_bug_count > 0:
                milestone_buglistings.append(
                    dict(
                        title=milestone.name,
                        url=canonical_url(milestone),
                        count=milestone_bug_count,
                        ))
        return milestone_buglistings


class BugTargetBugTagsView(LaunchpadView):
    """Helper methods for rendering the bug tags portlet."""

    def _getSearchURL(self, tag):
        """Return the search URL for the tag."""
        # Use path_only here to reduce the size of the rendered page.
        return "+bugs?field.tag=%s" % urllib.quote(tag)

    @property
    def tags_cloud_data(self):
        """The data for rendering a tags cloud"""
        official_tags = self.context.official_bug_tags
        tags = self.context.getUsedBugTagsWithOpenCounts(
            self.user, 10, official_tags)

        return sorted(
            [dict(
                tag=tag,
                count=count,
                url=self._getSearchURL(tag),
                )
            for (tag, count) in tags.iteritems()],
            key=itemgetter('count'), reverse=True)

    @property
    def show_manage_tags_link(self):
        """Should a link to a "manage official tags" page be shown?"""
        return (IOfficialBugTagTargetRestricted.providedBy(self.context) and
                check_permission('launchpad.BugSupervisor', self.context))


class OfficialBugTagsManageView(LaunchpadEditFormView):
    """View class for management of official bug tags."""

    schema = IOfficialBugTagTargetPublic
    custom_widget('official_bug_tags', LargeBugTagsWidget)

    @property
    def label(self):
        """The form label."""
        return 'Manage official bug tags for %s' % self.context.title

    @property
    def page_title(self):
        """The page title."""
        return self.label

    @action('Save', name='save')
    def save_action(self, action, data):
        """Action for saving new official bug tags."""
        self.context.official_bug_tags = data['official_bug_tags']
        self.next_url = canonical_url(self.context)

    @property
    def tags_js_data(self):
        """Return the JSON representation of the bug tags."""
        # The model returns dict and list respectively but dumps blows up on
        # security proxied objects.
        used_tags = removeSecurityProxy(
            self.context.getUsedBugTagsWithOpenCounts(self.user))
        official_tags = removeSecurityProxy(self.context.official_bug_tags)
        return """<script type="text/javascript">
                      var used_bug_tags = %s;
                      var official_bug_tags = %s;
                      var valid_name_pattern = %s;
                  </script>
               """ % (
               dumps(used_tags),
               dumps(official_tags),
               dumps(valid_name_pattern.pattern))

    @property
    def cancel_url(self):
        """The URL the user is sent to when clicking the "cancel" link."""
        return canonical_url(self.context)


class BugsVHostBreadcrumb(Breadcrumb):
    rootsite = 'bugs'
    text = 'Bugs'


class BugsPatchesView(LaunchpadView):
    """View list of patch attachments associated with bugs."""

    @property
    def label(self):
        """The display label for the view."""
        if IPerson.providedBy(self.context):
            return 'Patch attachments for %s' % self.context.displayname
        else:
            return 'Patch attachments in %s' % self.context.displayname

    @property
    def patch_task_orderings(self):
        """The list of possible sort orderings for the patches view.

        The orderings are a list of tuples of the form:
          [(DisplayName, InternalOrderingName), ...]
        For example:
          [("Patch age", "-latest_patch_uploaded"),
           ("Importance", "-importance"),
           ...]
        """
        orderings = [("patch age", "-latest_patch_uploaded"),
                     ("importance", "-importance"),
                     ("status", "status"),
                     ("oldest first", "datecreated"),
                     ("newest first", "-datecreated")]
        targetname = self.targetName()
        if targetname is not None:
            # Lower case for consistency with the other orderings.
            orderings.append((targetname.lower(), "targetname"))
        return orderings

    def batchedPatchTasks(self):
        """Return a BatchNavigator for bug tasks with patch attachments."""
        orderby = self.request.get("orderby", "-latest_patch_uploaded")
        if orderby not in [x[1] for x in self.patch_task_orderings]:
            raise UnexpectedFormData(
                "Unexpected value for field 'orderby': '%s'" % orderby)
        return BatchNavigator(
            self.context.searchTasks(
                None, user=self.user, order_by=orderby,
                status=UNRESOLVED_BUGTASK_STATUSES,
                omit_duplicates=True, has_patch=True),
            self.request)

    def targetName(self):
        """Return the name of the current context's target type, or None.

        The name is something like "Package" or "Project" (meaning
        Product); it is intended to be appropriate to use as a column
        name in a web page, for example.  If no target type is
        appropriate for the current context, then return None.
        """
        if (IDistribution.providedBy(self.context) or
            IDistroSeries.providedBy(self.context)):
            return "Package"
        elif (IProjectGroup.providedBy(self.context) or
              IPerson.providedBy(self.context)):
            # In the case of an IPerson, the target column can vary
            # row-by-row, showing both packages and products.  We
            # decided to go with the table header "Project" for both,
            # as its meaning is broad and could conceivably cover
            # packages too.  We also considered "Target", but rejected
            # it because it's used as a verb elsewhere in Launchpad's
            # UI, with a totally different meaning.  If anyone can
            # think of a better term than "Project", please JFDI here.
            return "Project"  # "Project" meaning Product, of course
        else:
            return None

    def patchAge(self, patch):
        """Return a timedelta object for the age of a patch attachment."""
        now = datetime.now(timezone('UTC'))
        return now - patch.message.datecreated

    def proxiedUrlForLibraryFile(self, patch):
        """Return the proxied download URL for a Librarian file."""
        return ProxiedLibraryFileAlias(patch.libraryfile, patch).http_url


class TargetSubscriptionView(LaunchpadView):
    """A view to show all a person's structural subscriptions to a target."""

    def initialize(self):
        super(TargetSubscriptionView, self).initialize()
        # Some resources such as help files are only provided on the bugs
        # rootsite.  So if we got here via another, possibly hand-crafted, URL
        # redirect to the equivalent URL on the bugs rootsite.
        if not BugsLayer.providedBy(self.request):
            new_url = urljoin(
                self.request.getRootURL('bugs'), self.request['PATH_INFO'])
            self.request.response.redirect(new_url)
            return
        expose_structural_subscription_data_to_js(
            self.context, self.request, self.user, self.subscriptions)

    @property
    def subscriptions(self):
        return get_structural_subscriptions_for_target(
            self.context, self.user)

    @property
    def label(self):
        return "Your subscriptions to %s" % (self.context.displayname,)

    page_title = label
