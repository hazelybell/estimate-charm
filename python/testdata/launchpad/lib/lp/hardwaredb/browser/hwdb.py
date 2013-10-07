# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'HWDBApplicationNavigation',
    'HWDBFingerprintSetView',
    'HWDBPersonSubmissionsView',
    'HWDBSubmissionTextView',
    'HWDBUploadView',
    ]

from textwrap import dedent

from z3c.ptcompat import ViewPageTemplateFile
from zope.component import getUtility
from zope.interface import implements
from zope.publisher.interfaces.browser import IBrowserPublisher

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.app.errors import NotFoundError
from lp.hardwaredb.interfaces.hwdb import (
    IHWDBApplication,
    IHWDeviceClassSet,
    IHWDeviceSet,
    IHWDriverSet,
    IHWSubmissionDeviceSet,
    IHWSubmissionForm,
    IHWSubmissionSet,
    IHWSystemFingerprintSet,
    IHWVendorIDSet,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.services.webapp import (
    LaunchpadView,
    Navigation,
    stepthrough,
    )
from lp.services.webapp.batching import BatchNavigator
from lp.services.webapp.interfaces import ILaunchBag


class HWDBUploadView(LaunchpadFormView):
    """View class for hardware database submissions."""

    schema = IHWSubmissionForm
    label = 'Hardware Database Submission'
    page_title = 'Submit New Data to the Launchpad Hardware Database'

    @action(u'Upload', name='upload')
    def upload_action(self, action, data):
        """Create a record in the HWSubmission table."""
        # We expect that the data submitted by the client contains
        # data for all fields defined in the form. The main client
        # which POSTs data to this URL, checkbox, sometimes omits
        # some fields (see bug 357316). The absence of required
        # fields is not caught by Zope's form validation -- it only
        # checks if required fields are not empty, and does this only
        # if these fields are present in the form data. Absent fields
        # are not detected, so let's do that here.
        expected_fields = set(self.schema.names())
        submitted_fields = set(data)
        missing_fields = expected_fields.difference(submitted_fields)
        if len(missing_fields) > 0:
            missing_fields = ', '.join(sorted(missing_fields))
            self.addCustomHeader(
                'Error: Required fields not contained in POST data: '
                + missing_fields)
            return

        distributionset = getUtility(IDistributionSet)
        distribution = distributionset.getByName(data['distribution'].lower())
        if distribution is not None:
            release = data['distroseries']
            architecture = data['architecture']
            try:
                distroseries = distribution.getSeries(release)
            except NotFoundError:
                self.addErrorHeader("distroseries",
                    "%s isn't a valid distribution series"
                     % data['distroseries'])
                return

            try:
                distroarchseries = distroseries[architecture]
            except NotFoundError:
                self.addErrorHeader("distroarchseries",
                    "%s isn't a valid distribution architecture"
                     % data['architecture'])
                return
        else:
            distroarchseries = None

        fingerprintset = getUtility(IHWSystemFingerprintSet)
        fingerprint = fingerprintset.getByName(data['system'])
        if fingerprint is None:
            fingerprint = fingerprintset.createFingerprint(data['system'])

        filesize = len(data['submission_data'])
        submission_file = self.request.form[
            self.widgets['submission_data'].name]
        submission_file.seek(0)
        # convert a filename with "path elements" to a regular filename
        filename = submission_file.filename.replace('/', '-')

        hw_submissionset = getUtility(IHWSubmissionSet)
        hw_submissionset.createSubmission(
            date_created=data['date_created'],
            format=data['format'],
            private=data['private'],
            contactable=data['contactable'],
            submission_key=data['submission_key'],
            emailaddress=data['emailaddress'],
            distroarchseries=distroarchseries,
            raw_submission=submission_file,
            filename=filename,
            filesize=filesize,
            system_fingerprint=data['system'])

        self.addCustomHeader('OK data stored')
        self.request.response.addNotification(
            "Thank you for your submission.")

    def render(self):
        """See ILaunchpadFormView."""
        if self.errors:
            self.setHeadersForHWDBClient()
        return LaunchpadFormView.render(self)

    def setHeadersForHWDBClient(self):
        """Add headers that help the HWDB client detect a successful upload.

        An upload is normally not made by a regular web browser, but by the
        HWDB client. In order to allow the client to easily detect a
        successful as well as an failed request, add some HTTP headers
        to the response.
        """
        for field in self.form_fields:
            field_name = field.__name__
            error = self.getFieldError(field_name)
            if error:
                self.addErrorHeader(field_name, error)

    def addErrorHeader(self, field_name, error):
        """Adds a header informing an error to automated clients."""
        return self.addCustomHeader(u"Error in field '%s' - %s" %
                                    (field_name, error))

    def addCustomHeader(self, value):
        """Adds a custom header to HWDB clients."""
        self.request.response.setHeader(
            u'X-Launchpad-HWDB-Submission', value)


class HWDBPersonSubmissionsView(LaunchpadView):
    """View class for preseting HWDB submissions by a person."""

    @property
    def label(self):
        return 'Hardware submissions for %s' % (self.context.title,)

    @property
    def page_title(self):
        return "Hardware Database submissions by %s" % (self.context.title,)

    def getAllBatched(self):
        """Return the list of HWDB submissions made by this person."""
        hw_submissionset = getUtility(IHWSubmissionSet)
        submissions = hw_submissionset.getByOwner(self.context, self.user)
        return BatchNavigator(submissions, self.request)

    def userIsOwner(self):
        """Return true, if self.context == self.user"""
        return self.context == self.user


class HWDBSubmissionTextView(LaunchpadView):
    """Renders a HWDBSubmission in parseable text."""
    def render(self):
        data = {}
        data["date_created"] = self.context.date_created
        data["date_submitted"] = self.context.date_submitted
        data["format"] = self.context.format.name

        dar = self.context.distroarchseries
        if dar:
            data["distribution"] = dar.distroseries.distribution.name
            data["distribution_series"] = dar.distroseries.version
            data["architecture"] = dar.architecturetag
        else:
            data["distribution"] = "(unknown)"
            data["distribution_series"] = "(unknown)"
            data["architecture"] = "(unknown)"

        data["system_fingerprint"] = (
            self.context.system_fingerprint.fingerprint)
        data["url"] = self.context.raw_submission.http_url

        return dedent("""
            Date-Created: %(date_created)s
            Date-Submitted: %(date_submitted)s
            Format: %(format)s
            Distribution: %(distribution)s
            Distribution-Series: %(distribution_series)s
            Architecture: %(architecture)s
            System: %(system_fingerprint)s
            Submission URL: %(url)s""" % data)


class HWDBApplicationNavigation(Navigation):
    """Navigation class for HWDBSubmissionSet."""

    usedfor = IHWDBApplication

    @stepthrough('+submission')
    def traverse_submission(self, name):
        user = getUtility(ILaunchBag).user
        submission = getUtility(IHWSubmissionSet).getBySubmissionKey(
            name, user=user)
        return submission

    @stepthrough('+fingerprint')
    def traverse_hwdb_fingerprint(self, name):
        return HWDBFingerprintSetView(self.context, self.request, name)

    @stepthrough('+device')
    def traverse_device(self, id):
        try:
            id = int(id)
        except ValueError:
            raise NotFoundError('invalid value for ID: %r' % id)
        return getUtility(IHWDeviceSet).getByID(id)

    @stepthrough('+deviceclass')
    def traverse_device_class(self, id):
        try:
            id = int(id)
        except ValueError:
            raise NotFoundError('invalid value for ID: %r' % id)
        return getUtility(IHWDeviceClassSet).get(id)

    @stepthrough('+driver')
    def traverse_driver(self, id):
        try:
            id = int(id)
        except ValueError:
            raise NotFoundError('invalid value for ID: %r' % id)
        return getUtility(IHWDriverSet).getByID(id)

    @stepthrough('+submissiondevice')
    def traverse_submissiondevice(self, id):
        try:
            id = int(id)
        except ValueError:
            raise NotFoundError('invalid value for ID: %r' % id)
        return getUtility(IHWSubmissionDeviceSet).get(id)

    @stepthrough('+hwvendorid')
    def traverse_hw_vendor_id(self, id):
        try:
            id = int(id)
        except ValueError:
            raise NotFoundError('invalid value for ID: %r' % id)
        return getUtility(IHWVendorIDSet).get(id)


class HWDBFingerprintSetView(LaunchpadView):
    """View class for lists of HWDB submissions for a system fingerprint."""

    implements(IBrowserPublisher)
    label = page_title = "Hardware Database submissions for a fingerprint"

    template = ViewPageTemplateFile(
        '../templates/hwdb-fingerprint-submissions.pt')

    def __init__(self, context,  request, system_name):
        LaunchpadView.__init__(self, context, request)
        self.system_name = system_name

    def getAllBatched(self):
        """A BatchNavigator instance with the submissions."""
        submissions = getUtility(IHWSubmissionSet).getByFingerprintName(
            self.system_name, self.user)
        return BatchNavigator(submissions, self.request)

    def browserDefault(self, request):
        """See `IBrowserPublisher`."""
        return self, ()

    def showOwner(self, submission):
        """Check if the owner can be shown in the list.
        """
        return (submission.owner is not None
                and (submission.contactable
                     or (submission.owner == self.user)))
