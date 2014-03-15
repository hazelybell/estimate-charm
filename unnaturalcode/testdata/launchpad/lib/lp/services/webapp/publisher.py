# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Publisher of objects as web pages.

"""

__metaclass__ = type
__all__ = [
    'DataDownloadView',
    'get_raw_form_value_from_current_request',
    'LaunchpadContainer',
    'LaunchpadView',
    'LaunchpadXMLRPCView',
    'canonical_name',
    'canonical_url',
    'canonical_url_iterator',
    'nearest',
    'Navigation',
    'rootObject',
    'stepthrough',
    'redirection',
    'stepto',
    'RedirectionView',
    'RenamedView',
    'UserAttributeCache',
    ]

from cgi import FieldStorage
import httplib
import re

from lazr.restful import (
    EntryResource,
    ResourceJSONEncoder,
    )
from lazr.restful.declarations import error_status
from lazr.restful.interfaces import IJSONRequestCache
from lazr.restful.tales import WebLayerAPI
from lazr.restful.utils import get_current_browser_request
import simplejson
from zope import i18n
from zope.app.publisher.xmlrpc import IMethodPublisher
from zope.component import (
    getUtility,
    queryMultiAdapter,
    )
from zope.component.interfaces import ComponentLookupError
from zope.i18nmessageid import Message
from zope.interface import (
    directlyProvides,
    implements,
    )
from zope.interface.advice import addClassAdvisor
from zope.publisher.defaultview import getDefaultViewName
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.browser import (
    IBrowserPublisher,
    IDefaultBrowserLayer,
    )
from zope.publisher.interfaces.xmlrpc import IXMLRPCView
from zope.security.checker import (
    NamesChecker,
    ProxyFactory,
    )
from zope.traversing.browser.interfaces import IAbsoluteURL

from lp.app.errors import NotFoundError
from lp.app.interfaces.informationtype import IInformationType
from lp.app.interfaces.launchpad import IPrivacy
from lp.app.versioninfo import revno
from lp.layers import (
    LaunchpadLayer,
    setFirstLayer,
    WebServiceLayer,
    )
from lp.services.encoding import is_ascii_only
from lp.services.features import (
    defaultFlagValue,
    getFeatureFlag,
    )
from lp.services.utils import obfuscate_structure
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchBag,
    ILaunchpadApplication,
    ILaunchpadContainer,
    ILaunchpadRoot,
    IOpenLaunchBag,
    IStructuredString,
    NoCanonicalUrl,
    )
from lp.services.webapp.url import urlappend
from lp.services.webapp.vhosts import allvhosts

# Monkeypatch NotFound to always avoid generating OOPS
# from NotFound in web service calls.
error_status(httplib.NOT_FOUND)(NotFound)

# Used to match zope namespaces eg ++model++.
RESERVED_NAMESPACE = re.compile('\\+\\+.*\\+\\+')


class DecoratorAdvisor:
    """Base class for a function decorator that adds class advice.

    The advice stores information in a magic attribute in the class's dict.
    The magic attribute's value is a dict, which contains names and functions
    that were set in the function decorators.
    """

    magic_class_attribute = None

    def __init__(self, name):
        self.name = name

    def __call__(self, fn):
        self.fn = fn
        addClassAdvisor(self.advise)
        return fn

    def getValueToStore(self):
        return self.fn

    def advise(self, cls):
        assert self.magic_class_attribute is not None, (
            'You must provide the magic_class_attribute to use')
        D = cls.__dict__.get(self.magic_class_attribute)
        if D is None:
            D = {}
            setattr(cls, self.magic_class_attribute, D)
        D[self.name] = self.getValueToStore()
        return cls


class stepthrough(DecoratorAdvisor):
    """Add the decorated method to stepthrough traversals for a class.

    A stepthrough method must take single argument that's the path segment for
    the object that it's returning. A common pattern is something like:

      @stepthrough('+foo')
      def traverse_foo(self, name):
          return getUtility(IFooSet).getByName(name)

    which looks up an object in IFooSet called 'name', allowing a URL
    traversal that looks like:

      launchpad.net/.../+foo/name

    See also doc/navigation.txt.

    This uses Zope's class advisor stuff to make sure that the path segment
    passed to `stepthrough` is handled by the decorated method.

    That is::
      cls.__stepthrough_traversals__[argument] = decorated
    """

    magic_class_attribute = '__stepthrough_traversals__'


class stepto(DecoratorAdvisor):
    """Add the decorated method to stepto traversals for a class.

    A stepto method must take no arguments and return an object for the URL at
    that point.

      @stepto('+foo')
      def traverse_foo(self):
          return getUtility(IFoo)

    which looks up an object for '+foo', allowing a URL traversal that looks
    like:

      launchpad.net/.../+foo

    See also doc/navigation.txt.

    This uses Zope's class advisor stuff to make sure that the path segment
    passed to `stepto` is handled by the decorated method.

    That is::
      cls.__stepto_traversals__[argument] = decorated
    """

    magic_class_attribute = '__stepto_traversals__'


class redirection:
    """A redirection is used for two related purposes.

    It is a class advisor in its two argument form or as a descriptor.
    It says what name is mapped to where.

    It is an object returned from a traversal method in its one argument
    form.  It says that the result of such traversal is a redirect.

    You can use the keyword argument 'status' to change the status code
    from the default of 303 (assuming http/1.1).
    """

    def __init__(self, arg1, arg2=None, status=None):
        if arg2 is None:
            self.fromname = None
            self.toname = arg1
        else:
            self.fromname = arg1
            self.toname = lambda self: arg2
            addClassAdvisor(self.advise)
        self.status = status

    def __call__(self, fn):
        # We are being used as a descriptor.
        assert self.fromname is None, (
            "redirection() can not be used as a descriptor in its "
            "two argument form")

        self.fromname = self.toname
        self.toname = fn
        addClassAdvisor(self.advise)

        return fn

    def advise(self, cls):
        redirections = cls.__dict__.get('__redirections__')
        if redirections is None:
            redirections = {}
            setattr(cls, '__redirections__', redirections)
        redirections[self.fromname] = (self.toname, self.status)
        return cls


class DataDownloadView:
    """Download data without templating.

    Subclasses must provide getBody, content_type and filename.
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        """Set the headers and return the body.

        It is not necessary to supply Content-length, because this is added by
        the caller.
        """
        self.request.response.setHeader('Content-Type', self.content_type)
        self.request.response.setHeader(
            'Content-Disposition', 'attachment; filename="%s"' % (
             self.filename))
        return self.getBody()


class UserAttributeCache:
    """Mix in to provide self.user, cached."""

    _no_user = object()
    _user = _no_user
    _account = _no_user

    @property
    def account(self):
        if self._account is self._no_user:
            self._account = getUtility(ILaunchBag).account
        return self._account

    @property
    def user(self):
        """The logged-in Person, or None if there is no one logged in."""
        if self._user is self._no_user:
            self._user = getUtility(ILaunchBag).user
        return self._user


class LaunchpadView(UserAttributeCache):
    """Base class for views in Launchpad.

    Available attributes and methods are:

    - context
    - request
    - initialize() <-- subclass this for specific initialization
    - template     <-- the template set from zcml, otherwise not present
    - user         <-- currently logged-in user
    - render()     <-- used to render the page.  override this if you have
                       many templates not set via zcml, or you want to do
                       rendering from Python.
    - publishTraverse() <-- override this to support traversing-through.
    - private      <-- used to indicate if the view contains private data.
                       override this if the view has special privacy needs
                       (i.e. context doesn't properly indicate privacy).
    """

    REDIRECTED_STATUSES = [201, 301, 302, 303, 307]

    @property
    def private(self):
        """A view is private if its context is."""
        privacy = IPrivacy(self.context, None)
        if privacy is not None:
            return privacy.private
        else:
            return False

    @property
    def information_type(self):
        """A view has the information_type of its context."""
        information_typed = IInformationType(self.context, None)
        if information_typed is None:
            return None
        return information_typed.information_type.title

    @property
    def information_type_description(self):
        """A view has the information_type_description of its context."""
        information_typed = IInformationType(self.context, None)
        if information_typed is None:
            return None
        return information_typed.information_type.description

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self._error_message = None
        self._info_message = None
        # FakeRequest does not have all properties required by the
        # IJSONRequestCache adapter.
        if isinstance(request, FakeRequest):
            return
        # Several view objects may be created for one page request:
        # One view for the main context and template, and other views
        # for macros included in the main template.
        cache = self._get_json_cache()
        if cache is None:
            return
        related_features = cache.setdefault('related_features', {})
        related_features.update(self.related_feature_info)

    def _get_json_cache(self):
        # Some tests create views without providing any request
        # object at all; other tests run without the component
        # infrastructure.
        try:
            cache = IJSONRequestCache(self.request).objects
        except TypeError as error:
            if error.args[0] == 'Could not adapt':
                cache = None
        return cache

    @property
    def beta_features(self):
        cache = self._get_json_cache()
        if cache is None:
            return []
        related_features = cache.setdefault('related_features', {}).values()
        return [f for f in related_features if f['is_beta']]

    def initialize(self):
        """Override this in subclasses.

        Default implementation does nothing.
        """
        pass

    @property
    def page_description(self):
        """Return a string containing a description of the context.

        Typically this is the contents of the most-descriptive text attribute
        of the context, by default its 'description' attribute if there is
        one.

        This will be inserted into the HTML meta description, and may
        eventually end up in search engine summary results, or when a link to
        the page is shared elsewhere.

        This may be specialized by view subclasses.

        Do not write eg "This is a page about...", just directly describe the
        object on the page.
        """
        return getattr(self.context, 'description', None)

    @property
    def template(self):
        """The page's template, if configured in zcml."""
        return self.index

    @property
    def yui_version(self):
        """The version of YUI we are using."""
        value = getFeatureFlag('js.yui_version')
        if not value:
            return 'yui'
        else:
            return value

    @property
    def yui_console_debug(self):
        """Hide console debug messages in production."""
        # We need to import here otherwise sitecustomize can't get imported,
        # likely due to some non-obvious circular import issues.
        from lp.services.config import config
        return 'true' if config.devmode else 'false'

    @property
    def combo_url(self):
        """Return the URL for the combo loader."""
        # Circular imports, natch.
        from lp.services.config import config
        combo_url = '/+combo'
        if not config.devmode:
            combo_url += '/rev%s' % revno
        return combo_url

    def render(self):
        """Return the body of the response.

        If the mime type of request.response starts with text/, then
        the result of this method is encoded to the charset of
        request.response. If there is no charset, it is encoded to
        utf8. Otherwise, the result of this method is treated as bytes.

        XXX: Steve Alexander says this is a convenient lie. That is, its
        not quite right, but good enough for most uses.
        """
        return self.template()

    def _isRedirected(self):
        """Return True if a redirect was requested.

        Check if the response status is one of 301, 302, 303 or 307.
        """
        return self.request.response.getStatus() in self.REDIRECTED_STATUSES

    def __call__(self):
        self.initialize()
        if self._isRedirected():
            # Don't render the page on redirects.
            return u''
        else:
            return self.render()

    def _getErrorMessage(self):
        """Property getter for `error_message`."""
        return self._error_message

    def _setErrorMessage(self, error_message):
        """Property setter for `error_message`.

        Enforces `error_message` values that are either None or
        implement IStructuredString.
        """
        if error_message != self._error_message:
            if (error_message is None or
                IStructuredString.providedBy(error_message)):
                # The supplied value is of a compatible type,
                # assign it to property backing variable.
                self._error_message = error_message
            else:
                raise ValueError(
                    '%s is not a valid value for error_message, only '
                    'None and IStructuredString are allowed.' %
                    type(error_message))

    error_message = property(_getErrorMessage, _setErrorMessage)

    def _getInfoMessage(self):
        """Property getter for `info_message`."""
        return self._info_message

    def _setInfoMessage(self, info_message):
        """Property setter for `info_message`.

        Enforces `info_message` values that are either None or
        implement IStructuredString.
        """
        if info_message != self._info_message:
            if (info_message is None or
                IStructuredString.providedBy(info_message)):
                # The supplied value is of a compatible type,
                # assign it to property backing variable.
                self._info_message = info_message
            else:
                raise ValueError(
                    '%s is not a valid value for info_message, only '
                    'None and IStructuredString are allowed.' %
                    type(info_message))

    info_message = property(_getInfoMessage, _setInfoMessage)

    def getCacheJSON(self):
        cache = dict(IJSONRequestCache(self.request).objects)
        if WebLayerAPI(self.context).is_entry:
            cache['context'] = self.context
        if self.user is None:
            cache = obfuscate_structure(cache)
        return simplejson.dumps(
            cache, cls=ResourceJSONEncoder,
            media_type=EntryResource.JSON_TYPE)

    def publishTraverse(self, request, name):
        """See IBrowserPublisher."""
        # By default, a LaunchpadView cannot be traversed through.
        # Those that can be must override this method.
        raise NotFound(self, name, request=request)

    @property
    def recommended_canonical_url(self):
        """Canonical URL to be recommended in metadata.

        Used to generate <link rel="canonical"> to hint that pages
        with different URLs are actually (at least almost) functionally
        and semantically identical.

        See http://www.google.com/support/webmasters/bin/\
            answer.py?answer=139394
        "Canonical is a long word that means my preferred or my
        primary."

        Google (at least) will primarily, but not absolutely certainly,
        treat these pages as duplicates, so don't use this if there's any
        real chance the user would want to specifically find one of the
        non-duplicate pages.

        Most views won't need this.
        """
        return None

    # Names of feature flags which affect a view.
    related_features = ()

    @property
    def related_feature_info(self):
        """Related feature flags that are active for this context and scope.

        This property describes all features marked as related_features in the
        view.  is_beta means that the value is not the default value.

        Return a dict of flags keyed by flag_name, with title and url as given
        by the flag's description.  Value is the value in the current scope,
        and is_beta is true if this is not the default value.
        """
        # Avoid circular imports.
        from lp.services.features.flags import flag_info

        beta_info = {}
        for (flag_name, value_domain, documentation, default_behavior, title,
             url) in flag_info:
            if flag_name not in self.related_features:
                continue
            value = getFeatureFlag(flag_name)
            beta_info[flag_name] = {
                'is_beta': (defaultFlagValue(flag_name) != value),
                'title': title,
                'url': url,
                'value': value,
            }
        return beta_info


class LaunchpadXMLRPCView(UserAttributeCache):
    """Base class for writing XMLRPC view code."""

    implements(IXMLRPCView, IMethodPublisher)

    def __init__(self, context, request):
        self.context = context
        self.request = request


class LaunchpadRootUrlData:
    """ICanonicalUrlData for the ILaunchpadRoot object."""

    implements(ICanonicalUrlData)

    path = ''
    inside = None
    rootsite = None

    def __init__(self, context):
        self.context = context


def canonical_urldata_iterator(obj):
    """Iterate over the urldata for the object and each of its canonical url
    parents.

    Raises NoCanonicalUrl if canonical url data is not available.
    """
    current_object = obj
    urldata = None
    # The while loop is to proceed the first time around because we're
    # on the initial object, and subsequent times, because there is an object
    # inside.
    while current_object is obj or urldata.inside is not None:
        urldata = ICanonicalUrlData(current_object, None)
        if urldata is None:
            raise NoCanonicalUrl(obj, current_object)
        yield urldata
        current_object = urldata.inside


def canonical_url_iterator(obj):
    """Iterate over the object and each of its canonical url parents.

    Raises NoCanonicalUrl if a canonical url is not available.
    """
    yield obj
    for urldata in canonical_urldata_iterator(obj):
        if urldata.inside is not None:
            yield urldata.inside


class CanonicalAbsoluteURL:
    """A bridge between Zope's IAbsoluteURL and Launchpad's canonical_url.

    We don't implement the whole interface; only what's needed to
    make absoluteURL() succceed.
    """
    implements(IAbsoluteURL)

    def __init__(self, context, request):
        """Initialize with respect to a context and request."""
        self.context = context
        self.request = request

    def __unicode__(self):
        """Returns the URL as a unicode string."""
        raise NotImplementedError()

    def __str__(self):
        """Returns an ASCII string with all unicode characters url quoted."""
        return canonical_url(self.context, self.request)

    def __repr__(self):
        """Get a string representation """
        raise NotImplementedError()

    __call__ = __str__


def layer_for_rootsite(rootsite):
    """Return the registered layer for the specified rootsite.

    'code' -> lp.code.publisher.CodeLayer
    'translations' -> lp.translations.publisher.TranslationsLayer
    et al.

    The layer is defined in ZCML using a named utility with the name of the
    rootsite, and providing IDefaultBrowserLayer.  If there is no utility
    defined with the specified name, then LaunchpadLayer is returned.
    """
    try:
        return getUtility(IDefaultBrowserLayer, rootsite)
    except ComponentLookupError:
        return LaunchpadLayer


class FakeRequest:
    """Used solely to provide a layer for the view check in canonical_url."""

    form_ng = None


def canonical_url(
    obj, request=None, rootsite=None, path_only_if_possible=False,
    view_name=None, force_local_path=False):
    """Return the canonical URL string for the object.

    If the canonical url configuration for the given object binds it to a
    particular root site, then we use that root URL.

    (There is an assumption here that traversal works the same way on
     different sites.  When that isn't so, we need to specify the url
     in full in the canonical url configuration.  We may want to
     register canonical url configuration *for* particular sites in the
     future, to allow more flexibility for traversal.
     I foresee a refactoring where we'll combine the concepts of
     sites, layers, URLs and so on.)

    Otherwise, we attempt to take the protocol, host and port from
    the request.  If a request is not provided, but a web-request is in
    progress, the protocol, host and port are taken from the current request.

    :param request: The web request; if not provided, canonical_url attempts
        to guess at the current request, using the protocol, host, and port
        taken from the root_url given in launchpad.conf.
    :param path_only_if_possible: If the protocol and hostname can be omitted
        for the current request, return a url containing only the path.
    :param view_name: Provide the canonical url for the specified view,
        rather than the default view.
    :param force_local_path: Strip off the site no matter what.
    :raises: NoCanonicalUrl if a canonical url is not available.
    """
    urlparts = [urldata.path
                for urldata in canonical_urldata_iterator(obj)
                if urldata.path]

    if rootsite is None:
        obj_urldata = ICanonicalUrlData(obj, None)
        if obj_urldata is None:
            raise NoCanonicalUrl(obj, obj)
        rootsite = obj_urldata.rootsite

    # The request is needed when there's no rootsite specified.
    if request is None:
        # Look for a request from the interaction.
        current_request = get_current_browser_request()
        if current_request is not None:
            if WebServiceLayer.providedBy(current_request):
                from lp.services.webapp.publication import (
                    LaunchpadBrowserPublication)
                from lp.services.webapp.servers import (
                    LaunchpadBrowserRequest)
                current_request = LaunchpadBrowserRequest(
                    current_request.bodyStream.getCacheStream(),
                    dict(current_request.environment))
                current_request.setPublication(
                    LaunchpadBrowserPublication(None))
                current_request.setVirtualHostRoot(names=[])
                main_root_url = current_request.getRootURL(
                    'mainsite')
                current_request._app_server = main_root_url.rstrip('/')

            request = current_request

    if view_name is not None:
        # Make sure that the view is registered for the site requested.
        fake_request = FakeRequest()
        directlyProvides(fake_request, layer_for_rootsite(rootsite))
        # Look first for a view.
        if queryMultiAdapter((obj, fake_request), name=view_name) is None:
            # Look if this is a special name defined by Navigation.
            navigation = queryMultiAdapter(
                (obj, fake_request), IBrowserPublisher)
            if isinstance(navigation, Navigation):
                all_names = navigation.all_traversal_and_redirection_names
            else:
                all_names = []
            if view_name not in all_names:
                raise AssertionError(
                    'Name "%s" is not registered as a view or navigation '
                    'step for "%s" on "%s".' % (
                        view_name, obj.__class__.__name__, rootsite))
        urlparts.insert(0, view_name)

    if request is None:
        # Yes this really does need to be here, as rootsite can be None, and
        # we don't want to make the getRootURL from the request break.
        if rootsite is None:
            rootsite = 'mainsite'
        root_url = allvhosts.configs[rootsite].rooturl
    else:
        root_url = request.getRootURL(rootsite)

    path = u'/'.join(reversed(urlparts))
    if ((path_only_if_possible and
         request is not None and
         root_url.startswith(request.getApplicationURL()))
        or force_local_path):
        return unicode('/' + path)
    return unicode(root_url + path)


def canonical_name(name):
    """Return the canonical form of a name used in a URL.

    This helps us to deal with common mistypings of URLs.
    Currently only accounts for uppercase letters.

    >>> canonical_name('ubuntu')
    'ubuntu'
    >>> canonical_name('UbUntU')
    'ubuntu'

    """
    return name.lower()


def nearest(obj, *interfaces):
    """Return the nearest object up the canonical url chain that provides
    one of the interfaces given.

    The object returned might be the object given as an argument, if that
    object provides one of the given interfaces.

    Return None is no suitable object is found or if there is no canonical_url
    defined for the object.
    """
    try:
        for current_obj in canonical_url_iterator(obj):
            for interface in interfaces:
                if interface.providedBy(current_obj):
                    return current_obj
        return None
    except NoCanonicalUrl:
        return None


def get_raw_form_value_from_current_request(field_name):
    # XXX: StevenK 2013-02-06 bug=1116954: We should not need to refetch
    # the file content from the request, since the passed in one has been
    # wrongly encoded.
    # Circular imports.
    from lp.services.webapp.servers import WebServiceClientRequest
    request = get_current_browser_request()
    assert isinstance(request, WebServiceClientRequest)
    # Zope wrongly encodes any form element that doesn't look like a file,
    # so re-fetch the file content if it has been encoded.
    if request and request.form.has_key(field_name) and isinstance(
        request.form[field_name], unicode):
        request._environ['wsgi.input'].seek(0)
        fs = FieldStorage(fp=request._body_instream, environ=request._environ)
        return fs[field_name].value


class RootObject:
    implements(ILaunchpadApplication, ILaunchpadRoot)


rootObject = ProxyFactory(RootObject(), NamesChecker(["__class__"]))


class LaunchpadContainer:
    implements(ILaunchpadContainer)

    def __init__(self, context):
        self.context = context

    def isWithin(self, scope):
        """Is this object within the given scope?

        By default all objects are only within itself.  More specific adapters
        must override this and implement the logic they want.
        """
        return self.context == scope


class Navigation:
    """Base class for writing browser navigation components.

    Note that the canonical_url part of Navigation is used outside of
    the browser context.
    """
    implements(IBrowserPublisher)

    def __init__(self, context, request=None):
        """Initialize with context and maybe with a request."""
        self.context = context
        self.request = request

    # Set this if you want to set a new layer before doing any traversal.
    newlayer = None

    def traverse(self, name):
        """Override this method to handle traversal.

        Raise NotFoundError if the name cannot be traversed.
        """
        raise NotFoundError(name)

    def redirectSubTree(self, target, status=301):
        """Redirect the subtree to the given target URL."""
        while True:
            nextstep = self.request.stepstogo.consume()
            if nextstep is None:
                break
            target = urlappend(target, nextstep)

        query_string = self.request.get('QUERY_STRING')
        if query_string:
            target = target + '?' + query_string

        return RedirectionView(target, self.request, status)

    # The next methods are for use by the Zope machinery.
    def publishTraverse(self, request, name):
        """Shim, to set objects in the launchbag when traversing them.

        This needs moving into the publication component, once it has been
        refactored.
        """
        # Launchpad only produces ascii URLs.  If the name is not ascii, we
        # can say nothing is found here.
        if not is_ascii_only(name):
            raise NotFound(self.context, name)
        nextobj = self._publishTraverse(request, name)
        getUtility(IOpenLaunchBag).add(nextobj)
        return nextobj

    def _combined_class_info(self, attrname):
        """Walk the class's __mro__ looking for attributes with the given
        name in class dicts.  Combine the values of these attributes into
        a single dict.  Return it.
        """
        combined_info = {}
        # Note that we want to give info from more specific classes priority
        # over info from less specific classes.  We can do this by walking
        # the __mro__ backwards, and using dict.update(...)
        for cls in reversed(type(self).__mro__):
            value = cls.__dict__.get(attrname)
            if value is not None:
                combined_info.update(value)
        return combined_info

    def _handle_next_object(self, nextobj, request, name):
        """Do the right thing with the outcome of traversal.

        If we have a redirection object, then redirect accordingly.

        If we have None, issue a NotFound error.

        Otherwise, return the object.
        """
        # Avoid circular imports.
        if nextobj is None:
            raise NotFound(self.context, name)
        elif isinstance(nextobj, redirection):
            return RedirectionView(
                nextobj.toname, request, status=nextobj.status)
        else:
            return nextobj

    @property
    def all_traversal_and_redirection_names(self):
        """Return the names of all the traversals and redirections defined."""
        all_names = set()
        all_names.update(self.stepto_traversals.keys())
        all_names.update(self.stepthrough_traversals.keys())
        all_names.update(self.redirections.keys())
        return list(all_names)

    @property
    def stepto_traversals(self):
        """Return a dictionary containing all the stepto names defined."""
        return self._combined_class_info('__stepto_traversals__')

    @property
    def stepthrough_traversals(self):
        """Return a dictionary containing all the stepthrough names defined.
        """
        return self._combined_class_info('__stepthrough_traversals__')

    @property
    def redirections(self):
        """Return a dictionary containing all the redirections names defined.
        """
        return self._combined_class_info('__redirections__')

    def _publishTraverse(self, request, name):
        """Traverse, like zope wants."""

        # First, set a new layer if there is one.  This is important to do
        # first so that if there's an error, we get the error page for
        # this request.
        if self.newlayer is not None:
            setFirstLayer(request, self.newlayer)

        # Next, see if we're being asked to stepto somewhere.
        stepto_traversals = self.stepto_traversals
        if stepto_traversals is not None:
            if name in stepto_traversals:
                handler = stepto_traversals[name]
                try:
                    nextobj = handler(self)
                except NotFoundError:
                    nextobj = None

                return self._handle_next_object(nextobj, request, name)

        # Next, see if we have at least two path steps in total to traverse;
        # that is, the current name and one on the request's traversal stack.
        # If so, see if the name is in the namespace_traversals, and if so,
        # dispatch to the appropriate function.  We can optimise by changing
        # the order of these checks around a bit.
        # If the next path step is a zope namespace eg ++model++, then we
        # actually do not want to process the path steps as a stepthrough
        # traversal so we just ignore it here.
        namespace_traversals = self.stepthrough_traversals
        if namespace_traversals is not None:
            if name in namespace_traversals:
                stepstogo = request.stepstogo
                if stepstogo:
                    # First peek at the nextstep to see if we should ignore it.
                    nextstep = stepstogo.peek()
                    if not RESERVED_NAMESPACE.match(nextstep):
                        nextstep = stepstogo.consume()
                        handler = namespace_traversals[name]
                        try:
                            nextobj = handler(self, nextstep)
                        except NotFoundError:
                            nextobj = None
                        else:
                            # Circular import; breaks make.
                            from lp.services.webapp.breadcrumb import (
                                Breadcrumb,
                            )
                            stepthrough_page = queryMultiAdapter(
                                    (self.context, self.request), name=name)
                            if stepthrough_page:
                                # Not all stepthroughs have a page; if they
                                # don't, there's no need for a breadcrumb.
                                page_title = getattr(
                                    stepthrough_page, 'page_title', None)
                                label = getattr(
                                    stepthrough_page, 'label', None)
                                stepthrough_text = page_title or label
                                if isinstance(stepthrough_text, Message):
                                    stepthrough_text = i18n.translate(
                                        stepthrough_text,
                                        context=self.request)
                                stepthrough_url = canonical_url(
                                    self.context, view_name=name)
                                stepthrough_breadcrumb = Breadcrumb(
                                    context=self.context,
                                    url=stepthrough_url,
                                    text=stepthrough_text)
                                self.request.traversed_objects.append(
                                    stepthrough_breadcrumb)

                        return self._handle_next_object(nextobj, request,
                            nextstep)

        # Next, look up views on the context object.  If a view exists,
        # use it.
        view = queryMultiAdapter((self.context, request), name=name)
        if view is not None:
            return view

        # Next, look up redirections.  Note that registered views take
        # priority over redirections, because you can always make your
        # view redirect, but you can't make your redirection 'view'.
        redirections = self.redirections
        if redirections is not None:
            if name in redirections:
                urlto, status = redirections[name]
                return RedirectionView(urlto(self), request, status=status)

        # Finally, use the self.traverse() method.  This can return
        # an object to be traversed, or raise NotFoundError.  It must not
        # return None.
        try:
            nextobj = self.traverse(name)
        except NotFoundError:
            nextobj = None
        return self._handle_next_object(nextobj, request, name)

    def browserDefault(self, request):
        view_name = getDefaultViewName(self.context, request)
        return self.context, (view_name, )


class RedirectionView:
    implements(IBrowserPublisher)

    def __init__(self, target, request, status=None, cache_view=None):
        self.target = target
        self.request = request
        self.status = status
        self.cache_view = cache_view

    def initialize(self):
        if self.cache_view:
            self.cache_view.initialize()

    def getCacheJSON(self):
        if self.cache_view:
            return self.cache_view.getCacheJSON()
        else:
            return simplejson.dumps({})

    def __call__(self):
        self.request.response.redirect(self.target, status=self.status)
        return u''

    def browserDefault(self, request):
        return self, ()


class RenamedView:
    """Redirect permanently to the new name of the view.

    This view should be used when pages are renamed.

    :param new_name: the new page name.
    :param rootsite: (optional) the virtual host to redirect to,
            e.g. 'answers'.
    """
    implements(IBrowserPublisher)

    def __init__(self, context, request, new_name, rootsite=None):
        self.context = context
        self.request = request
        self.new_name = new_name
        self.rootsite = rootsite

    def __call__(self):
        context_url = canonical_url(self.context, rootsite=self.rootsite)
        # Prevents double slashes on the root object.
        if context_url.endswith('/'):
            target_url = "%s%s" % (context_url, self.new_name)
        else:
            target_url = "%s/%s" % (context_url, self.new_name)

        query_string = self.request.get('QUERY_STRING', '')
        if query_string:
            target_url += '?' + query_string

        self.request.response.redirect(target_url, status=301)

        return u''

    def publishTraverse(self, request, name):
        """See zope.publisher.interfaces.browser.IBrowserPublisher."""
        raise NotFound(self.context, name)

    def browserDefault(self, request):
        """See zope.publisher.interfaces.browser.IBrowserPublisher."""
        return self, ()
