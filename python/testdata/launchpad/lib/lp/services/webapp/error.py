# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'InvalidBatchSizeView',
    'NotFoundView',
    'ProtocolErrorView',
    'ReadOnlyErrorView',
    'RequestExpiredView',
    'SystemErrorView',
    'TranslationUnavailableView',
    'UnexpectedFormDataView',
    ]


import httplib
import sys
import traceback

from z3c.ptcompat import ViewPageTemplateFile
from zope.browser.interfaces import ISystemErrorView
from zope.component import getUtility
from zope.exceptions.exceptionformatter import format_exception
from zope.interface import implements

import lp.layers
from lp.services import features
from lp.services.config import config
from lp.services.features.flags import NullFeatureController
from lp.services.propertycache import cachedproperty
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.publisher import LaunchpadView


class SystemErrorView(LaunchpadView):
    """Helper class for views on exceptions.

    Also, sets a 500 response code.
    """
    implements(ISystemErrorView)

    page_title = 'Error: Launchpad system error'

    plain_oops_template = ViewPageTemplateFile(
        'templates/oops-veryplain.pt')

    # Override this in subclasses.  A value of None means "don't set this"
    response_code = httplib.INTERNAL_SERVER_ERROR

    show_tracebacks = False
    debugging = False
    specialuser = False

    # For the UI 1.0, we'll be wanting to try out fancy error pages of
    # various kinds so, those particular pages will need to fully render.
    # For example, like special 404 pages.
    # So we need to mark those particular error handling views as safe
    # for fully rendering by checking that there is no way to get that
    # error if the user is unauthorized to use the server in restircted mode.
    #
    # Set this value to True in subclasses where the error cannot possibly
    # be shown to unauthorized visitors.
    safe_to_show_in_restricted_mode = False

    def __init__(self, context, request):
        super(SystemErrorView, self).__init__(context, request)
        self.request.response.removeAllNotifications()
        if self.response_code is not None:
            self.request.response.setStatus(self.response_code)
        if getattr(self.request, 'oopsid') is not None:
            self.request.response.addHeader(
                'X-Lazr-OopsId', self.request.oopsid)

        # Need to neuter the feature flags on error output. The base template
        # checks for a feature flag, but they depend on db access which might
        # not have been setup yet.
        request.features = NullFeatureController()
        features.install_feature_controller(request.features)

        self.computeDebugOutput()
        if config.canonical.show_tracebacks:
            self.show_tracebacks = True
        if lp.layers.DebugLayer.providedBy(self.request):
            self.debugging = True
        self.specialuser = getUtility(ILaunchBag).developer

    def isSystemError(self):
        """See zope.browser.interfaces import ISystemErrorView

        It appears that returning True from this method means the
        exception is logged as a SiteError.
        """
        return True

    def computeDebugOutput(self):
        """Inspect the exception, and set up instance attributes.

        self.error_type
        self.error_object
        self.traceback_lines
        self.htmltext
        """
        self.error_type, self.error_object, tb = sys.exc_info()
        try:
            self.traceback_lines = traceback.format_tb(tb)
            self.htmltext = '\n'.join(
                format_exception(self.error_type, self.error_object,
                                 tb, as_html=True)
                )
        finally:
            del tb

    def inside_div(self, html):
        """Returns the given HTML inside a div of an appropriate class."""

        return ('<div class="highlight" style="'
                "font-family: 'Ubuntu Mono', monospace;"
                ' font-size: smaller;">'
                '%s'
                '</div>') % html

    def maybeShowTraceback(self):
        """Return a traceback, but only if it is appropriate to do so."""
        # If the config says to show tracebacks, or we're on the debug port,
        # or the logged in user is in the launchpad team, show tracebacks.
        if self.show_tracebacks or self.debugging or self.specialuser:
            return self.inside_div(self.htmltext)
        else:
            return ''

    @property
    def oops_id_text(self):
        """Return the OOPS ID, linkified if appropriate."""
        oopsid = self.request.oopsid
        oops_root_url = config.launchpad.oops_root_url
        oops_code = '<code class="oopsid">%s</code>' % oopsid
        if self.specialuser:
            # The logged-in user is a Launchpad Developer,
            # so linkify the OOPS
            return '<a href="%s%s">%s</a>' % (
                oops_root_url, oopsid, oops_code)
        else:
            return oops_code

    def __call__(self):
        if (config.launchpad.restrict_to_team and
              not self.safe_to_show_in_restricted_mode):
            return self.plain_oops_template()
        else:
            return self.index()

    @property
    def layer_help(self):
        if lp.layers.FeedsLayer.providedBy(self.request):
            return '''<a href="https://help.launchpad.net/Feeds">
                      Help with Launchpad feeds</a>'''
        else:
            return None


class ProtocolErrorView(SystemErrorView):
    """View for protocol errors.

    Problems to do with an HTTP request that need to be handled more
    subtly than with a 500 response code. Used to handle a
    `ProtocolErrorException`.
    """

    def __call__(self):
        """Set the appropriate status code and headers."""
        exception = self.context
        self.request.response.setStatus(exception.status)
        for header, value in exception.headers.items():
            self.request.response.setHeader(header, value)
        return self.index()


class UnexpectedFormDataView(SystemErrorView):

    page_title = 'Error: Unexpected form data'


class NotFoundView(SystemErrorView):

    page_title = 'Error: Page not found'

    response_code = httplib.NOT_FOUND

    def __call__(self):
        return self.index()

    @cachedproperty
    def referrer(self):
        """If there is a referring page, return its URL.

        Otherwise return None.
        """
        referrer = self.request.get('HTTP_REFERER')
        if referrer:
            # Since this is going to be included in the page template it will
            # be coerced into unicode.  The byte string representation
            # 'should' be ascii, but often it isn't.  The only use for this is
            # to show a link back to the referring site, so we can't use
            # replace or ignore.  Best to just pretent it doesn't exist.
            try:
                return unicode(referrer)
            except UnicodeDecodeError:
                return None
        else:
            return None


class GoneView(NotFoundView):
    """The page is gone, such as a page belonging to a suspended user."""

    page_title = 'Error: Page gone'

    response_code = httplib.GONE


class RequestExpiredView(SystemErrorView):

    page_title = 'Error: Timeout'

    response_code = httplib.SERVICE_UNAVAILABLE

    def __init__(self, context, request):
        SystemErrorView.__init__(self, context, request)
        # Set Retry-After header to 15 minutes. Hard coded because this
        # is really just a guess and I don't think any clients actually
        # pay attention to it - it is just a hint.
        request.response.setHeader('Retry-After', 900)


class InvalidBatchSizeView(SystemErrorView):
    """View rendered when an InvalidBatchSizeError is raised."""

    page_title = "Error: Invalid Batch Size"

    response_code = httplib.BAD_REQUEST

    def isSystemError(self):
        """We don't need to log these errors in the SiteLog."""
        return False

    @property
    def error_message(self):
        """Return the error message from the exception."""
        if len(self.context.args) > 0:
            return self.context.args[0]
        return ""


class TranslationUnavailableView(SystemErrorView):

    page_title = 'Error: Translation page is not available'

    response_code = httplib.SERVICE_UNAVAILABLE

    def __call__(self):
        return self.index()


class ReadOnlyErrorView(SystemErrorView):
    """View rendered when an InvalidBatchSizeError is raised."""

    page_title = "Error: you can't do this right now"

    response_code = httplib.SERVICE_UNAVAILABLE

    def isSystemError(self):
        """We don't need to log these errors in the SiteLog."""
        return False

    def __call__(self):
        return self.index()


class NoReferrerErrorView(SystemErrorView):
    """View rendered when a POST request does not include a REFERER header."""

    response_code = httplib.FORBIDDEN


class OpenIdDiscoveryFailureView(SystemErrorView):

    response_code = httplib.SERVICE_UNAVAILABLE

    def isSystemError(self):
        """We don't need to log these errors in the SiteLog."""
        return False


class DisconnectionErrorView(SystemErrorView):

    response_code = httplib.SERVICE_UNAVAILABLE
    reason = u'our database being temporarily offline'


class OperationalErrorView(DisconnectionErrorView):

    reason = u'our database having temporary operational issues'
