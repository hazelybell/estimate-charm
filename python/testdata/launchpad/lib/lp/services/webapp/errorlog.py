# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Error logging facilities."""

__metaclass__ = type

import contextlib
from itertools import repeat
import operator
import re
import urlparse

from lazr.restful.utils import (
    get_current_browser_request,
    safe_hasattr,
    )
import oops.createhooks
import oops_amqp
from oops_datedir_repo import DateDirRepo
import oops_datedir_repo.serializer
import oops_timeline
import pytz
from zope.component.interfaces import ObjectEvent
from zope.error.interfaces import IErrorReportingUtility
from zope.event import notify
from zope.exceptions.exceptionformatter import format_exception
from zope.interface import implements
from zope.publisher.interfaces.xmlrpc import IXMLRPCRequest
from zope.traversing.namespace import view

from lp.app import versioninfo
from lp.layers import WebServiceLayer
from lp.services.config import config
from lp.services.messaging import rabbit
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.webapp.adapter import (
    get_request_duration,
    soft_timeout_expired,
    )
from lp.services.webapp.interfaces import (
    IErrorReport,
    IErrorReportEvent,
    IErrorReportRequest,
    IUnloggedException,
    )
from lp.services.webapp.opstats import OpStats
from lp.services.webapp.pgsession import PGSessionBase
from lp.services.webapp.vhosts import allvhosts


UTC = pytz.utc

LAZR_OOPS_USER_REQUESTED_KEY = 'lazr.oops.user_requested'


def _is_sensitive(request, name):
    """Return True if the given request variable name is sensitive.

    Sensitive request variables should not be recorded in OOPS
    reports.  Currently we consider the following to be sensitive:
     * any name containing 'password' or 'passwd'
     * cookies
     * the HTTP_COOKIE header.
    """
    upper_name = name.upper()
    # Block passwords
    if ('PASSWORD' in upper_name or 'PASSWD' in upper_name):
        return True

    # Block HTTP_COOKIE and oauth_signature.
    if name in ('HTTP_COOKIE', 'oauth_signature'):
        return True

    # Allow remaining UPPERCASE names and remaining form variables.  Note that
    # XMLRPC requests won't have a form attribute.
    form = getattr(request, 'form', [])
    if name == upper_name or name in form:
        return False

    # Block everything else
    return True


class ErrorReportEvent(ObjectEvent):
    """A new error report has been created."""
    implements(IErrorReportEvent)


class ErrorReport:
    implements(IErrorReport)

    def __init__(self, id, type, value, time, tb_text, username,
                 url, duration, req_vars, timeline, informational=None,
                 branch_nick=None, revno=None, topic=None, reporter=None):
        self.id = id
        self.type = type
        self.value = value
        self.time = time
        self.topic = topic
        if reporter is not None:
            self.reporter = reporter
        self.tb_text = tb_text
        self.username = username
        self.url = url
        self.duration = duration
        # informational is ignored - will be going from the oops module
        # soon too.
        self.req_vars = req_vars
        self.timeline = timeline
        self.branch_nick = branch_nick or versioninfo.branch_nick
        self.revno = revno or versioninfo.revno

    def __repr__(self):
        return '<ErrorReport %s %s: %s>' % (self.id, self.type, self.value)

    @classmethod
    def read(cls, fp):
        # Deprecated: use the oops module directly now, when possible.
        report = oops_datedir_repo.serializer.read(fp)
        return cls(**report)


def notify_publisher(report):
    if not report.get('id'):
        report['id'] = str(id(report))
    notify(ErrorReportEvent(report))
    return report['id']


def attach_adapter_duration(report, context):
    # More generic than HTTP requests - e.g. how long a script was running
    # for.
    report['duration'] = get_request_duration()


def attach_exc_info(report, context):
    """Attach exception info to the report.

    This reads the 'exc_info' key from the context and sets the:
    * type
    * value
    * tb_text
    keys in the report.
    """
    info = context.get('exc_info')
    if info is None:
        return
    report['type'] = getattr(info[0], '__name__', info[0])
    report['value'] = oops.createhooks.safe_unicode(info[1])
    if not isinstance(info[2], basestring):
        tb_text = ''.join(format_exception(*info,
                                           **{'as_html': False}))
    else:
        tb_text = info[2]
    report['tb_text'] = tb_text


_ignored_exceptions_for_unauthenticated_users = set(['Unauthorized'])


def attach_previous_oopsid(report, context):
    """Add a link to the previous OOPS generated this request, if any."""
    request = context.get('http_request')
    last_oopsid = getattr(request, 'oopsid', None)
    if last_oopsid is not None:
        report['last_oops'] = last_oopsid


def attach_feature_info(report, context):
    """Attach info about the active features and scopes."""
    request = context.get('http_request')
    features = getattr(request, 'features', None)
    if features is not None:
        report['features.usedFlags'] = u'%r' % features.usedFlags()
        report['features.usedScopes'] = u'%r' % features.usedScopes()


def attach_http_request(report, context):
    """Add request metadata into the error report.

    This reads the exc_info and http_request keys from the context and will
    write to:
    * url
    * ignore
    * username
    * topic
    * req_vars
    """
    info = context.get('exc_info')
    request = context.get('http_request')
    if request is None:
        return
    # XXX jamesh 2005-11-22: Temporary fix, which Steve should
    #      undo. URL is just too HTTPRequest-specific.
    if safe_hasattr(request, 'URL'):
        # URL's are byte strings, but possibly str() will fail - safe_unicode
        # handles all those cases, and then we can safely encode it to utf8.
        # This is strictly double handling as a URL should never have unicode
        # characters in it anyway (though it may have them % encoded, which is
        # fine). Better safe than sorry, and the safe_unicode handling won't
        # cause double-encoding, so it is safe.
        url = oops.createhooks.safe_unicode(request.URL).encode('utf8')
        report['url'] = url

    if WebServiceLayer.providedBy(request) and info is not None:
        webservice_error = getattr(
            info[1], '__lazr_webservice_error__', 500)
        if webservice_error / 100 != 5:
            request.oopsid = None
            # Tell the oops machinery to ignore this error
            report['ignore'] = True

    missing = object()
    principal = getattr(request, 'principal', missing)
    if safe_hasattr(principal, 'getLogin'):
        login = principal.getLogin()
    elif principal is missing or principal is None:
        # Request has no principal (e.g. scriptrequest)
        login = None
    else:
        # Request has an UnauthenticatedPrincipal.
        login = 'unauthenticated'
        if _get_type(report) in (
            _ignored_exceptions_for_unauthenticated_users):
            report['ignore'] = True

    if principal is not None and principal is not missing:
        username = ', '.join([
                unicode(login),
                unicode(request.principal.id),
                unicode(request.principal.title),
                unicode(request.principal.description)])
        report['username'] = username

    if getattr(request, '_orig_env', None):
        report['topic'] = request._orig_env.get('launchpad.pageid', '')

    for key, value in request.items():
        if _is_sensitive(request, key):
            value = '<hidden>'
        if not isinstance(value, basestring):
            value = oops.createhooks.safe_unicode(value)
        # keys need to be unicode objects. The form items (a subset of
        # request.items) are generally just the url query_string url decoded,
        # which means the keys may be invalid in bson docs (bson requires that
        # they be unicode).
        key = oops.createhooks.safe_unicode(key)
        report['req_vars'][key] = value
    if IXMLRPCRequest.providedBy(request):
        args = request.getPositionalArguments()
        # Request variables are strings: this could move to its own key and be
        # raw.
        report['req_vars']['xmlrpc args'] = unicode(args)


def attach_ignore_from_exception(report, context):
    """Set the ignore key to True if the excception is ignored."""
    info = context.get('exc_info')
    if info is None:
        return
    # Because of IUnloggedException being a sidewards lookup we must
    # capture this here to filter on later.
    report['ignore'] = IUnloggedException.providedBy(info[1])


def _filter_session_statement(database_id, statement):
    """Replace quoted strings with '%s' in statements on session DB."""
    if database_id == 'SQL-' + PGSessionBase.store_name:
        return re.sub("'[^']*'", "'%s'", statement)
    else:
        return statement


def filter_sessions_timeline(report, context):
    """Filter timeline session data in the report."""
    timeline = report.get('timeline')
    if timeline is None:
        return
    statements = []
    for event in timeline:
        start, end, category, detail = event[:4]
        detail = _filter_session_statement(category, detail)
        statements.append((start, end, category, detail) + event[4:])
    report['timeline'] = statements


def _get_type(report):
    return report.get('type', 'No exception type')


class ErrorReportingUtility:
    implements(IErrorReportingUtility)

    _ignored_exceptions = set(['TranslationUnavailable', 'NoReferrerError'])
    _ignored_exceptions_for_offsite_referer = set([
        'GoneError', 'InvalidBatchSizeError', 'NotFound'])
    _default_config_section = 'error_reports'

    def __init__(self):
        self.configure()
        self._oops_messages = {}
        self._oops_message_key_iter = (
            index for index, _ignored in enumerate(repeat(None)))

    def configure(self, section_name=None, config_factory=oops.Config,
            publisher_adapter=None):
        """Configure the utility using the named section from the config.

        The 'error_reports' section is used if section_name is None.
        """
        if section_name is None:
            section_name = self._default_config_section
        self._oops_config = config_factory()
        # We use the timeline module
        oops_timeline.install_hooks(self._oops_config)
        #
        # What do we want in our reports?
        # Constants:
        self._oops_config.template['branch_nick'] = versioninfo.branch_nick
        self._oops_config.template['revno'] = versioninfo.revno
        reporter = config[self._default_config_section].oops_prefix
        if section_name != self._default_config_section:
            reporter = '%s-%s' % (reporter, section_name)
        self._oops_config.template['reporter'] = reporter
        # Should go in an HTTP module.
        self._oops_config.template['req_vars'] = {}
        # Exceptions, with the zope formatter.
        self._oops_config.on_create.append(attach_exc_info)
        # Ignore IUnloggedException exceptions
        self._oops_config.on_create.append(attach_ignore_from_exception)
        # Zope HTTP requests have lots of goodies.
        self._oops_config.on_create.append(attach_http_request)
        # We don't want session cookie values in the report - they contain
        # authentication keys.
        self._oops_config.on_create.append(filter_sessions_timeline)
        # We permit adding messages during the execution of a script (not
        # threadsafe - so only scripts) - a todo item is to only add this
        # for scripts (or to make it threadsafe)
        self._oops_config.on_create.append(self._attach_messages)
        # In the zope environment we track how long a script / http
        # request has been running for - this is useful data!
        self._oops_config.on_create.append(attach_adapter_duration)
        # Any previous OOPS reports generated this request.
        self._oops_config.on_create.append(attach_previous_oopsid)
        # And any active feature flags.
        self._oops_config.on_create.append(attach_feature_info)

        def add_publisher(publisher):
            if publisher_adapter is not None:
                publisher = publisher_adapter(publisher)
            self._oops_config.publishers.append(publisher)

        # If amqp is configured we want to publish over amqp.
        if (config.error_reports.error_exchange and rabbit.is_configured()):
            exchange = config.error_reports.error_exchange
            routing_key = config.error_reports.error_queue_key
            amqp_publisher = oops_amqp.Publisher(
                rabbit.connect, exchange, routing_key)
            add_publisher(amqp_publisher)
        # We want to publish reports to disk for gathering to the central
        # analysis server, but only if we haven't already published to rabbit.
        self._oops_datedir_repo = DateDirRepo(
            config[self._default_config_section].error_dir)
        add_publisher(oops.publish_new_only(self._oops_datedir_repo.publish))
        # And send everything within the zope application server (only for
        # testing).
        add_publisher(notify_publisher)
        #
        # Reports are filtered if:
        #  - There is a key 'ignore':True in the report. This is set during
        #    _makeReport.
        self._oops_config.filters.append(
                operator.methodcaller('get', 'ignore'))
        #  - have a type listed in self._ignored_exceptions.
        self._oops_config.filters.append(
                lambda report: _get_type(report) in self._ignored_exceptions)
        #  - have a missing or offset REFERER header with a type listed in
        #    self._ignored_exceptions_for_offsite_referer
        self._oops_config.filters.append(self._filter_bad_urls_by_referer)

    @property
    def oops_prefix(self):
        """Get the current effective oops prefix."""
        return self._oops_config.template['reporter']

    def raising(self, info, request=None):
        """See IErrorReportingUtility.raising()"""
        context = dict(exc_info=info)
        if request is not None:
            context['http_request'] = request
        # In principle the timeline is per-request, but see bug=623199 -
        # at this point the request is optional, but get_request_timeline
        # does not care; when it starts caring, we will always have a
        # request object (or some annotations containing object).
        # RBC 20100901
        timeline = get_request_timeline(request)
        if timeline is not None:
            context['timeline'] = timeline
        report = self._oops_config.create(context)
        if self._oops_config.publish(report) is None:
            return
        if request:
            request.oopsid = report.get('id')
            request.oops = report
        return report

    def _filter_bad_urls_by_referer(self, report):
        """Filter if the report was generated because of a bad offsite url."""
        if _get_type(report) in self._ignored_exceptions_for_offsite_referer:
            was_http = report.get('url', '').lower().startswith('http')
            if was_http:
                req_vars = report.get('req_vars', {})
                referer = req_vars.get('HTTP_REFERER')
                # If there is no referrer then either the user has refer
                # disabled, or its someone coming from offsite or from some
                # saved bookmark. Any which way, its not a sign of a current
                # broken-url-generator in LP: ignore it.
                if referer is None:
                    return True
                referer_parts = urlparse.urlparse(referer)
                root_parts = urlparse.urlparse(
                    allvhosts.configs['mainsite'].rooturl)
                if root_parts.netloc not in referer_parts.netloc:
                    return True
        return False

    def _attach_messages(self, report, context):
        """merges self._oops_messages into the report req_vars variable."""
        # XXX AaronBentley 2009-11-26 bug=488950: There should be separate
        # storage for oops messages.
        req_vars = report['req_vars']
        for key, message in self._oops_messages.items():
            req_vars['<oops-message-%d>' % key] = str(message)

    @contextlib.contextmanager
    def oopsMessage(self, message):
        """Add an oops message to be included in oopses from this context.

        The message will be removed when the scope is exited, so this is
        useful for messages that are relevant only to errors raised during
        part of the request.

        Warning: This is not threadsafe at present, because there is only one
        ErrorReportingUtility per process.

        :param message: Unicode message.
        """
        key = self.addOopsMessage(message)
        try:
            yield
        finally:
            del self._oops_messages[key]

    def addOopsMessage(self, message):
        """Add a message to the current oops accumulator.

        Warning: This is not threadsafe at present, because there is only one
        ErrorReportingUtility per process.

        :param message: Unicode message.
        :returns: Key for this message.
        """
        key = self._oops_message_key_iter.next()
        self._oops_messages[key] = message
        return key


globalErrorUtility = ErrorReportingUtility()


class ErrorReportRequest:
    implements(IErrorReportRequest)

    oopsid = None


class ScriptRequest(ErrorReportRequest):
    """Fake request that can be passed to ErrorReportingUtility.raising.

    It can be used by scripts to enrich error reports with context information
    and a representation of the resource on which the error occurred. It also
    gives access to the generated OOPS id.

    The resource for which the error occurred MAY be identified by an URL.
    This URL should point to a human-readable representation of the model
    object, such as a page on launchpad.net, even if this URL does not occur
    as part of the normal operation of the script.

    :param data: context information relevant to diagnosing the error. It is
        recorded as request-variables in the OOPS.
    :type data: iterable of (key, value) tuples. Keys need not be unique.
    :param URL: initial value of the URL instance variable.

    :ivar URL: pointer to a representation of the resource for which the error
        occured. Defaults to None.
    :ivar oopsid: the oopsid set by ErrorReportingUtility.raising. Initially
        set to None.
    """

    def __init__(self, data, URL=None):
        self._data = list(data)
        self.oopsid = None
        self.URL = URL

    def items(self):
        return self._data

    @property
    def form(self):
        return dict(self.items())


class SoftRequestTimeout(Exception):
    """Soft request timeout expired"""


def end_request(event):
    # if no OOPS has been generated at the end of the request, but
    # the soft timeout has expired, log an OOPS.
    if event.request.oopsid is None and soft_timeout_expired():
        OpStats.stats['soft timeouts'] += 1
        globalErrorUtility.raising(
            (SoftRequestTimeout, SoftRequestTimeout(event.object), None),
            event.request)


class UserRequestOops(Exception):
    """A user requested OOPS to log statements."""


def maybe_record_user_requested_oops():
    """If an OOPS has been requested, report one.

    It will be stored in request.oopsid.
    """
    request = get_current_browser_request()
    # If there's a request and no existing OOPS, but an OOPS has been
    # requested, record one.
    if (request is not None
        and request.oopsid is None
        and request.annotations.get(LAZR_OOPS_USER_REQUESTED_KEY, False)):
        globalErrorUtility.raising(
            (UserRequestOops, UserRequestOops(), None), request)


class OopsNamespace(view):
    """A namespace handle traversals with ++oops++."""

    def traverse(self, name, ignored):
        """Record that an oops has been requested and return the context."""
        # Store the oops request in the request annotations.
        self.request.annotations[LAZR_OOPS_USER_REQUESTED_KEY] = True
        return self.context
