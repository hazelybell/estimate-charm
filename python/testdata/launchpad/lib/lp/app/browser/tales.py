# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation of the lp: htmlform: fmt: namespaces in TALES."""

__metaclass__ = type

from bisect import bisect
from datetime import (
    datetime,
    timedelta,
    )
from email.Utils import formatdate
import math
import os.path
import rfc822
import sys
from textwrap import dedent
import urllib

from lazr.enum import enumerated_type_registry
from lazr.restful.utils import get_current_browser_request
from lazr.uri import URI
import pytz
from z3c.ptcompat import ViewPageTemplateFile
from zope.component import (
    adapts,
    getMultiAdapter,
    getUtility,
    queryAdapter,
    )
from zope.error.interfaces import IErrorReportingUtility
from zope.interface import (
    Attribute,
    implements,
    Interface,
    )
from zope.publisher.browser import BrowserView
from zope.publisher.defaultview import getDefaultViewName
from zope.schema import TextLine
from zope.security.interfaces import Unauthorized
from zope.security.proxy import isinstance as zope_isinstance
from zope.traversing.interfaces import (
    IPathAdapter,
    ITraversable,
    TraversalError,
    )

from lp import _
from lp.app.browser.badge import IHasBadges
from lp.app.browser.stringformatter import FormattersAPI
from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.app.interfaces.launchpad import (
    IHasIcon,
    IHasLogo,
    IHasMugshot,
    IPrivacy,
    )
from lp.blueprints.interfaces.specification import ISpecification
from lp.blueprints.interfaces.sprint import ISprint
from lp.bugs.interfaces.bug import IBug
from lp.buildmaster.enums import BuildStatus
from lp.code.interfaces.branch import IBranch
from lp.layers import LaunchpadLayer
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.services.utils import total_seconds
from lp.services.webapp.authorization import check_permission
from lp.services.webapp.canonicalurl import nearest_adapter
from lp.services.webapp.error import SystemErrorView
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.webapp.interfaces import (
    IApplicationMenu,
    IContextMenu,
    IFacetMenu,
    ILaunchBag,
    INavigationMenu,
    IPrimaryContext,
    NoCanonicalUrl,
    )
from lp.services.webapp.menu import (
    get_current_view,
    get_facet,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    nearest,
    )
from lp.services.webapp.session import get_cookie_domain
from lp.services.webapp.url import urlappend
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.interfaces.archive import (
    IArchive,
    IPPA,
    )
from lp.soyuz.interfaces.binarypackagename import IBinaryAndSourcePackageName


SEPARATOR = ' : '


def format_link(obj, view_name=None, empty_value='None'):
    """Return the equivalent of obj/fmt:link as a string."""
    if obj is None:
        return empty_value
    adapter = queryAdapter(obj, IPathAdapter, 'fmt')
    link = getattr(adapter, 'link', None)
    if link is None:
        raise NotImplementedError("Missing link function on adapter.")
    return link(view_name)


class MenuLinksDict(dict):
    """A dict class to construct menu links when asked for and not before.

    We store all the information we need to construct the requested links,
    including the menu object and request url.
    """

    def __init__(self, menu, request_url, request):
        self._request_url = request_url
        self._menu = menu
        self._all_link_names = []
        self._extra_link_names = []
        dict.__init__(self)

        # The object has the facet, but does not have a menu, this
        # is probably the overview menu with is the default facet.
        if menu is None or getattr(menu, 'disabled', False):
            return
        menu.request = request

        # We get all the possible link names for the menu.
        # The link names are the defined menu links plus any extras.
        self._all_link_names = list(menu.links)
        extras = menu.extra_attributes
        if extras is not None:
            self._extra_link_names = list(extras)
            self._all_link_names.extend(extras)

    def __getitem__(self, link_name):
        if not link_name in self._all_link_names:
            raise KeyError(link_name)

        link = dict.get(self, link_name, None)
        if link is None:
            if link_name in self._extra_link_names:
                link = getattr(self._menu, link_name, None)
            else:
                link = self._menu.initLink(link_name, self._request_url)

        if not link_name in self._extra_link_names:
            self._menu.updateLink(link, self._request_url)

        self[link_name] = link
        return link

    def __delitem__(self, key):
        self._all_link_names.remove(key)
        dict.__delitem__(self, key)

    def items(self):
        return zip(self._all_link_names, self.values())

    def values(self):
        return [self[key] for key in self._all_link_names]

    def keys(self):
        return self._all_link_names

    def iterkeys(self):
        return iter(self._all_link_names)
    __iter__ = iterkeys


class MenuAPI:
    """Namespace to give access to the facet menus.

    The facet menu can be accessed with an expression like:

        tal:define="facetmenu view/menu:facet"

    which gives the facet menu of the nearest object along the canonical url
    chain that has an IFacetMenu adapter.
    """

    def __init__(self, context):
        self._tales_context = context
        if zope_isinstance(context, (LaunchpadView, BrowserView)):
            # The view is a LaunchpadView or a SimpleViewClass from a
            # template. The facet is added to the call by the ZCML.
            self.view = context
            self._context = self.view.context
            self._request = self.view.request
            self._selectedfacetname = getattr(
                self.view, '__launchpad_facetname__', None)
        else:
            self._context = context
            self._request = get_current_browser_request()
            self.view = None
            self._selectedfacetname = None

    def __getattribute__(self, facet):
        """Retrieve the links associated with a facet.

        It's used with expressions like context/menu:bugs/subscribe.

        :return: A dictionary mapping the link name to the associated Link
            object.
        :raise AttributeError: when there is no application menu for the
            facet.
        """
        # Use __getattribute__ instead of __getattr__, since __getattr__
        # gets called if any of the other properties raise an AttributeError,
        # which makes troubleshooting confusing. The has_facet can't easily
        # be placed first, since all the properties it uses would need to
        # be retrieved with object.__getattribute().
        missing = object()
        if (getattr(MenuAPI, facet, missing) is not missing
            or facet in object.__getattribute__(self, '__dict__')):
            return object.__getattribute__(self, facet)

        has_facet = object.__getattribute__(self, '_has_facet')
        if not has_facet(facet):
            raise AttributeError(facet)
        menu = queryAdapter(self._context, IApplicationMenu, facet)
        if menu is None:
            menu = queryAdapter(self._context, INavigationMenu, facet)
        links = self._getMenuLinksAndAttributes(menu)
        object.__setattr__(self, facet, links)
        return links

    def _getMenuLinksAndAttributes(self, menu):
        """Return a dict of the links and attributes of the menu."""
        return MenuLinksDict(menu, self._request_url(), self._request)

    def _has_facet(self, facet):
        """Does the object have the named facet?"""
        menu = self._facet_menu()
        if menu is None:
            return False
        return facet in menu.links

    def _request_url(self):
        request = self._request
        if request is None:
            return None
        request_urlobj = URI(request.getURL())
        # If the default view name is being used, we will want the url
        # without the default view name.
        defaultviewname = getDefaultViewName(self._context, request)
        if request_urlobj.path.rstrip('/').endswith(defaultviewname):
            request_urlobj = URI(request.getURL(1))
        query = request.get('QUERY_STRING')
        if query:
            request_urlobj = request_urlobj.replace(query=query)
        return request_urlobj

    def facet(self):
        """Return the IFacetMenu links related to the context."""
        menu = self._facet_menu()
        if menu is None:
            return []
        menu.request = self._request
        return list(menu.iterlinks(
            request_url=self._request_url(),
            selectedfacetname=self._selectedfacetname))

    def _facet_menu(self):
        """Return the IFacetMenu related to the context."""
        try:
            try:
                context = IPrimaryContext(self._context).context
            except TypeError:
                # Could not adapt raises a type error.  If there was no
                # way to adapt, then just use self._context.
                context = self._context
            menu = nearest_adapter(context, IFacetMenu)
        except NoCanonicalUrl:
            menu = None

        return menu

    def selectedfacetname(self):
        if self._selectedfacetname is None:
            return 'unknown'
        else:
            return self._selectedfacetname

    @property
    def context(self):
        menu = IContextMenu(self._context, None)
        return self._getMenuLinksAndAttributes(menu)

    @property
    def navigation(self):
        """Navigation menu links list."""
        try:
            # NavigationMenus may be associated with a content object or one
            # of its views. The context we need is the one from the TAL
            # expression.
            context = self._tales_context
            if self._selectedfacetname is not None:
                selectedfacetname = self._selectedfacetname
            else:
                # XXX sinzui 2008-05-09 bug=226917: We should be retrieving
                # the facet name from the layer implemented by the request.
                view = get_current_view(self._request)
                selectedfacetname = get_facet(view)
            try:
                menu = nearest_adapter(
                    context, INavigationMenu, name=selectedfacetname)
            except NoCanonicalUrl:
                menu = None
            return self._getMenuLinksAndAttributes(menu)
        except AttributeError as e:
            # If this method gets an AttributeError, we rethrow it as a
            # AssertionError. Otherwise, zope will hide the root cause
            # of the error and just say that "navigation" can't be traversed.
            new_exception = AssertionError(
                'AttributError in MenuAPI.navigation: %s' % e)
            # We cannot use parens around the arguments to `raise`,
            # since that will cause it to ignore the third argument,
            # which is the original traceback.
            new_exception.addinfo(sys.exc_info()[2])
            raise


class CountAPI:
    """Namespace to provide counting-related functions, such as length.

    This is available for all objects.  Individual operations may fail for
    objects that do not support them.
    """

    def __init__(self, context):
        self._context = context

    def len(self):
        """somelist/count:len  gives you an int that is len(somelist)."""
        return len(self._context)


class EnumValueAPI:
    """Namespace to test the value of an EnumeratedType Item.

    The value is given in the next path step.

        tal:condition="somevalue/enumvalue:BISCUITS"

    Registered for canonical.lazr.enum.Item.
    """
    implements(ITraversable)

    def __init__(self, item):
        self.item = item

    def traverse(self, name, furtherPath):
        if self.item.name == name:
            return True
        else:
            # Check whether this was an allowed value for this
            # enumerated type.
            enum = self.item.enum
            try:
                enum.getTermByToken(name)
            except LookupError:
                raise TraversalError(
                    'The enumerated type %s does not have a value %s.' %
                    (enum.name, name))
            return False


class HTMLFormAPI:
    """HTML form helper API, available as request/htmlform:.

    Use like:

        request/htmlform:fieldname/selected/literalvalue

        if request.form[fieldname] == literalvalue:
            return "selected"
        else:
            return None

    """
    implements(ITraversable)

    def __init__(self, request):
        self.form = request.form

    def traverse(self, name, furtherPath):
        if len(furtherPath) == 1:
            operation = furtherPath.pop()
            return HTMLFormOperation(self.form.get(name), operation)
        else:
            operation = furtherPath.pop()
            value = furtherPath.pop()
            if htmlmatch(self.form.get(name), value):
                return operation
            else:
                return None


def htmlmatch(formvalue, value):
    value = str(value)
    if isinstance(formvalue, list):
        return value in formvalue
    else:
        return formvalue == value


class HTMLFormOperation:

    implements(ITraversable)

    def __init__(self, formvalue, operation):
        self.formvalue = formvalue
        self.operation = operation

    def traverse(self, name, furtherPath):
        if htmlmatch(self.formvalue, name):
            return self.operation
        else:
            return None


class IRequestAPI(Interface):
    """Launchpad lp:... API available for an IApplicationRequest."""

    person = Attribute("The IPerson for the request's principal.")
    cookie_scope = Attribute("The scope parameters for cookies.")


class RequestAPI:
    """Adapter from IApplicationRequest to IRequestAPI."""
    implements(IRequestAPI)

    def __init__(self, request):
        self.request = request

    @property
    def person(self):
        return IPerson(self.request.principal, None)

    @property
    def cookie_scope(self):
        params = '; Path=/'
        uri = URI(self.request.getURL())
        if uri.scheme == 'https':
            params += '; Secure'
        domain = get_cookie_domain(uri.host)
        if domain is not None:
            params += '; Domain=%s' % domain
        return params


class DBSchemaAPI:
    """Adapter from integers to things that can extract information from
    DBSchemas.
    """
    implements(ITraversable)

    def __init__(self, number):
        self._number = number

    def traverse(self, name, furtherPath):
        if name in enumerated_type_registry:
            enum = enumerated_type_registry[name]
            return enum.items[self._number].title
        else:
            raise TraversalError(name)


class NoneFormatter:
    """Adapter from None to various string formats.

    In general, these will return an empty string.  They are provided for ease
    of handling NULL values from the database, which become None values for
    attributes in content classes.
    """
    implements(ITraversable)

    allowed_names = set([
        'approximatedate',
        'approximateduration',
        'break-long-words',
        'date',
        'datetime',
        'displaydate',
        'isodate',
        'email-to-html',
        'exactduration',
        'lower',
        'nice_pre',
        'nl_to_br',
        'pagetitle',
        'rfc822utcdatetime',
        'text-to-html',
        'time',
        'url',
        'link',
        ])

    def __init__(self, context):
        self.context = context

    def traverse(self, name, furtherPath):
        if name == 'shorten':
            if not len(furtherPath):
                raise TraversalError(
                    "you need to traverse a number after fmt:shorten")
            # Remove the maxlength from the path as it is a parameter
            # and not another traversal command.
            furtherPath.pop()
            return ''
        # We need to check to see if the name has been augmented with optional
        # evaluation parameters, delimited by ":". These parameters are:
        #  param1 = rootsite (used with link and url)
        #  param2 = default value (in case of context being None)
        # We are interested in the default value (param2).
        result = ''
        for nm in self.allowed_names:
            if name.startswith(nm + ":"):
                name_parts = name.split(":")
                name = name_parts[0]
                if len(name_parts) > 2:
                    result = name_parts[2]
                break
        if name in self.allowed_names:
            return result
        else:
            raise TraversalError(name)


class ObjectFormatterAPI:
    """Adapter for any object to a formatted string."""

    implements(ITraversable)

    # Although we avoid mutables as class attributes, the two ones below are
    # constants, so it's not a problem. We might want to use something like
    # frozenset (http://code.activestate.com/recipes/414283/) here, though.
    # The names which can be traversed further (e.g context/fmt:url/+edit).
    traversable_names = {
        'api_url': 'api_url',
        'link': 'link',
        'url': 'url',
        }

    # Names which are allowed but can't be traversed further.
    final_traversable_names = {
        'pagetitle': 'pagetitle',
        'global-css': 'global_css',
        }

    def __init__(self, context):
        self._context = context

    def url(self, view_name=None, rootsite=None):
        """Return the object's canonical URL.

        :param view_name: If not None, return the URL to the page with that
            name on this object.
        :param rootsite: If not None, return the URL to the page on the
            specified rootsite.  Note this is available only for subclasses
            that allow specifying the rootsite.
        """
        try:
            url = canonical_url(
                self._context, path_only_if_possible=True,
                rootsite=rootsite, view_name=view_name)
        except Unauthorized:
            url = ""
        return url

    def api_url(self, context):
        """Return the object's (partial) canonical web service URL.

        This method returns everything that goes after the web service version
        number.  Effectively the canonical URL but only the relative part with
        no site.
        """
        try:
            url = canonical_url(self._context, force_local_path=True)
        except Unauthorized:
            url = ""
        return url

    def traverse(self, name, furtherPath):
        """Traverse the specified path, processing any optional parameters.

        Up to 2 parameters are currently supported, and the path name will be
        of the form:
            name:param1:param2
        where
            param1 = rootsite (only used for link and url paths).
            param2 = default (used when self.context is None). The context
                     is not None here so this parameter is ignored.
        """
        if name.startswith('link:') or name.startswith('url:'):
            name_parts = name.split(':')
            name = name_parts[0]
            rootsite = name_parts[1]
            if rootsite != '':
                extra_path = None
                if len(furtherPath) > 0:
                    extra_path = '/'.join(reversed(furtherPath))
                # Remove remaining entries in furtherPath so that traversal
                # stops here.
                del furtherPath[:]
                if name == 'link':
                    if rootsite is None:
                        return self.link(extra_path)
                    else:
                        return self.link(extra_path, rootsite=rootsite)
                else:
                    if rootsite is None:
                        self.url(extra_path)
                    else:
                        return self.url(extra_path, rootsite=rootsite)
        if '::' in name:
            name = name.split(':')[0]
        if name in self.traversable_names:
            if len(furtherPath) >= 1:
                extra_path = '/'.join(reversed(furtherPath))
                del furtherPath[:]
            else:
                extra_path = None
            method_name = self.traversable_names[name]
            return getattr(self, method_name)(extra_path)
        elif name in self.final_traversable_names:
            method_name = self.final_traversable_names[name]
            return getattr(self, method_name)()
        else:
            raise TraversalError(name)

    def link(self, view_name, rootsite=None):
        """Return an HTML link to the object's page.

        The link consists of an icon followed by the object's name.

        :param view_name: If not None, the link will point to the page with
            that name on this object.
        :param rootsite: If not None, return the URL to the page on the
            specified rootsite.  Note this is available only for subclasses
            that allow specifying the rootsite.
        """
        raise NotImplementedError(
            "No link implementation for %r, IPathAdapter implementation "
            "for %r." % (self, self._context))

    def global_css(self):
        css_classes = set([])
        view = self._context

        # XXX: Bug #1076074
        private = getattr(view, 'private', False)
        if private:
            css_classes.add('private')
        else:
            css_classes.add('public')
        beta = getattr(view, 'beta_features', [])
        if beta:
            css_classes.add('beta')
        return ' '.join(list(css_classes))

    def _getSaneBreadcrumbDetail(self, breadcrumb):
        text = breadcrumb.detail
        if len(text) > 64:
            truncated = '%s...' % text[0:64]
            if truncated.count(u'\u201c') > truncated.count(u'\u201cd'):
                # Close the open smartquote if it was dropped.
                truncated += u'\u201d'
            return truncated
        return text

    def pagetitle(self):
        """The page title to be used.

        By default, reverse breadcrumbs are always used if they are available.
        If not available, then the view's .page_title attribut is used.
        """
        ROOT_TITLE = 'Launchpad'
        view = self._context
        request = get_current_browser_request()
        hierarchy_view = getMultiAdapter(
            (view.context, request), name='+hierarchy')
        if (isinstance(view, SystemErrorView) or
            hierarchy_view is None or
            not hierarchy_view.display_breadcrumbs):
            # The breadcrumbs are either not available or are overridden.  If
            # the view has a .page_title attribute use that.
            page_title = getattr(view, 'page_title', None)
            if page_title is not None:
                return page_title
            # If there is no template for the view, just use the default
            # Launchpad title.
            template = getattr(view, 'template', None)
            if template is None:
                template = getattr(view, 'index', None)
                if template is None:
                    return ROOT_TITLE
        # Use the reverse breadcrumbs.
        breadcrumbs = list(reversed(hierarchy_view.items))
        if len(breadcrumbs) == 0:
            # This implies there are no breadcrumbs, but this more often
            # is caused when an Unauthorized error is being raised.
            return ''
        detail_breadcrumb = self._getSaneBreadcrumbDetail(breadcrumbs[0])
        title_breadcrumbs = [breadcrumb.text for breadcrumb in breadcrumbs[1:]]
        title_text = SEPARATOR.join([detail_breadcrumb] + title_breadcrumbs)
        return FormattersAPI(title_text).obfuscate_email()


class ObjectImageDisplayAPI:
    """Base class for producing the HTML that presents objects
    as an icon, a logo, a mugshot or a set of badges.
    """

    def __init__(self, context):
        self._context = context

    #def default_icon_resource(self, context):
    def sprite_css(self):
        """Return the CSS class for the sprite"""
        # XXX: mars 2008-08-22 bug=260468
        # This should be refactored.  We shouldn't have to do type-checking
        # using interfaces.
        context = self._context
        sprite_string = None
        if IProduct.providedBy(context):
            sprite_string = 'product'
        elif IProjectGroup.providedBy(context):
            sprite_string = 'project'
        elif IPerson.providedBy(context):
            if context.is_team:
                sprite_string = 'team'
            else:
                if context.is_valid_person:
                    sprite_string = 'person'
                else:
                    sprite_string = 'person-inactive'
        elif IDistribution.providedBy(context):
            sprite_string = 'distribution'
        elif IDistributionSourcePackage.providedBy(context):
            sprite_string = 'package-source'
        elif ISprint.providedBy(context):
            sprite_string = 'meeting'
        elif IBug.providedBy(context):
            sprite_string = 'bug'
        elif IPPA.providedBy(context):
            if context.enabled:
                sprite_string = 'ppa-icon'
            else:
                sprite_string = 'ppa-icon-inactive'
        elif IArchive.providedBy(context):
            sprite_string = 'distribution'
        elif IBranch.providedBy(context):
            sprite_string = 'branch'
        elif ISpecification.providedBy(context):
            sprite_string = 'blueprint'
        elif IBinaryAndSourcePackageName.providedBy(context):
            sprite_string = 'package-source'

        if sprite_string is None:
            return None
        else:
            if hasattr(context, 'private') and context.private:
                sprite_string = sprite_string + ' private'

            return "sprite %s" % sprite_string

    def default_logo_resource(self, context):
        # XXX: mars 2008-08-22 bug=260468
        # This should be refactored.  We shouldn't have to do type-checking
        # using interfaces.
        if IProjectGroup.providedBy(context):
            return '/@@/project-logo'
        elif IPerson.providedBy(context):
            if context.is_team:
                return '/@@/team-logo'
            else:
                if context.is_valid_person:
                    return '/@@/person-logo'
                else:
                    return '/@@/person-inactive-logo'
        elif IProduct.providedBy(context):
            return '/@@/product-logo'
        elif IDistribution.providedBy(context):
            return '/@@/distribution-logo'
        elif ISprint.providedBy(context):
            return '/@@/meeting-logo'
        return None

    def default_mugshot_resource(self, context):
        # XXX: mars 2008-08-22 bug=260468
        # This should be refactored.  We shouldn't have to do type-checking
        # using interfaces.
        if IProjectGroup.providedBy(context):
            return '/@@/project-mugshot'
        elif IPerson.providedBy(context):
            if context.is_team:
                return '/@@/team-mugshot'
            else:
                if context.is_valid_person:
                    return '/@@/person-mugshot'
                else:
                    return '/@@/person-inactive-mugshot'
        elif IProduct.providedBy(context):
            return '/@@/product-mugshot'
        elif IDistribution.providedBy(context):
            return '/@@/distribution-mugshot'
        elif ISprint.providedBy(context):
            return '/@@/meeting-mugshot'
        return None

    def custom_icon_url(self):
        """Return the URL for this object's icon."""
        context = self._context
        if IHasIcon.providedBy(context) and context.icon is not None:
            icon_url = context.icon.getURL()
            return icon_url
        elif context is None:
            return ''
        else:
            return None

    def icon(self):
        #XXX: this should go away as soon as all image:icon where replaced
        return None

    def logo(self):
        """Return the appropriate <img> tag for this object's logo.

        :return: A string, or None if the context object doesn't have
            a logo.
        """
        context = self._context
        if not IHasLogo.providedBy(context):
            context = nearest(context, IHasLogo)
        if context is None:
            # we use the Launchpad logo for anything which is in no way
            # related to a Pillar (for example, a buildfarm)
            url = '/@@/launchpad-logo'
        elif context.logo is not None:
            url = context.logo.getURL()
        else:
            url = self.default_logo_resource(context)
            if url is None:
                # We want to indicate that there is no logo for this
                # object.
                return None
        logo = '<img alt="" width="64" height="64" src="%s" />'
        return logo % url

    def mugshot(self):
        """Return the appropriate <img> tag for this object's mugshot.

        :return: A string, or None if the context object doesn't have
            a mugshot.
        """
        context = self._context
        assert IHasMugshot.providedBy(context), 'No Mugshot for this item'
        if context.mugshot is not None:
            url = context.mugshot.getURL()
        else:
            url = self.default_mugshot_resource(context)
            if url is None:
                # We want to indicate that there is no mugshot for this
                # object.
                return None
        mugshot = """<img alt="" class="mugshot"
            width="192" height="192" src="%s" />"""
        return mugshot % url

    def badges(self):
        raise NotImplementedError(
            "Badge display not implemented for this item")

    def boolean(self):
        """Return an icon representing the context as a boolean value."""
        if bool(self._context):
            icon = 'yes'
        else:
            icon = 'no'
        markup = '<span class="sprite %(icon)s action-icon">%(icon)s</span>'
        return markup % dict(icon=icon)


class BugTaskImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IBugTask objects to a formatted string. This inherits
    from the generic ObjectImageDisplayAPI and overrides the icon
    presentation method.

    Used for image:icon.
    """
    implements(ITraversable)

    allowed_names = set([
        'icon',
        'logo',
        'mugshot',
        'badges',
        'sprite_css',
        ])

    icon_template = (
        '<span alt="%s" title="%s" class="%s"></span>')

    linked_icon_template = (
        '<a href="%s" alt="%s" title="%s" class="%s"></a>')

    def traverse(self, name, furtherPath):
        """Special-case traversal for icons with an optional rootsite."""
        if name in self.allowed_names:
            return getattr(self, name)()
        else:
            raise TraversalError(name)

    def sprite_css(self):
        """Return the CSS class for the sprite"""
        if self._context.importance:
            importance = self._context.importance.title.lower()
            return "sprite bug-%s" % importance
        else:
            return "sprite bug"

    def icon(self):
        """Display the icon dependent on the IBugTask.importance."""
        if self._context.importance:
            importance = self._context.importance.title.lower()
            alt = "(%s)" % importance
            title = importance.capitalize()
            if importance not in ("undecided", "wishlist"):
                # The other status names do not make a lot of sense on
                # their own, so tack on a noun here.
                title += " importance"
            css = "sprite bug-%s" % importance
        else:
            alt = ""
            title = ""
            css = self.sprite_css()

        return self.icon_template % (alt, title, css)

    def _hasBugBranch(self):
        """Return whether the bug has a branch linked to it."""
        return not self._context.bug.linked_branches.is_empty()

    def _hasSpecification(self):
        """Return whether the bug is linked to a specification."""
        return not self._context.bug.specifications.is_empty()

    def _hasPatch(self):
        """Return whether the bug has a patch."""
        return self._context.bug.has_patches

    def badges(self):
        badges = []
        information_type = self._context.bug.information_type
        if information_type in PRIVATE_INFORMATION_TYPES:
            badges.append(self.icon_template % (
                information_type.title, information_type.description,
                "sprite private"))

        if self._hasBugBranch():
            badges.append(self.icon_template % (
                "branch", "Branch exists", "sprite branch"))

        if self._hasSpecification():
            badges.append(self.icon_template % (
                "blueprint", "Related to a blueprint", "sprite blueprint"))

        if self._context.milestone:
            milestone_text = "milestone %s" % self._context.milestone.name
            badges.append(self.linked_icon_template % (
                canonical_url(self._context.milestone),
                milestone_text, "Linked to %s" % milestone_text,
                "sprite milestone"))

        if self._hasPatch():
            badges.append(self.icon_template % (
                "haspatch", "Has a patch", "sprite haspatch-icon"))

        # Join with spaces to avoid the icons smashing into each other
        # when multiple ones are presented.
        return " ".join(badges)


class BugTaskListingItemImageDisplayAPI(BugTaskImageDisplayAPI):
    """Formatter for image:badges for BugTaskListingItem.

    The BugTaskListingItem has some attributes to decide whether a badge
    should be displayed, which don't require a DB query when they are
    accessed.
    """

    def _hasBugBranch(self):
        """See `BugTaskImageDisplayAPI`"""
        return self._context.has_bug_branch

    def _hasSpecification(self):
        """See `BugTaskImageDisplayAPI`"""
        return self._context.has_specification

    def _hasPatch(self):
        """See `BugTaskImageDisplayAPI`"""
        return self._context.has_patch


class QuestionImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IQuestion to a formatted string. Used for image:icon."""

    def sprite_css(self):
        return "sprite question"


class SpecificationImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for ISpecification objects to a formatted string. This inherits
    from the generic ObjectImageDisplayAPI and overrides the icon
    presentation method.

    Used for image:icon.
    """

    icon_template = (
        '<span alt="%s" title="%s" class="%s" />')

    def sprite_css(self):
        """Return the CSS class for the sprite"""
        sprite_str = "sprite blueprint"

        if self._context.priority:
            priority = self._context.priority.title.lower()
            sprite_str = sprite_str + "-%s" % priority

        if self._context.private:
            sprite_str = sprite_str + ' private'

        return sprite_str

    def badges(self):

        badges = ''

        if len(self._context.linked_branches) > 0:
            badges += self.icon_template % (
                "branch", "Branch is available", "sprite branch")

        if self._context.informational:
            badges += self.icon_template % (
                "informational", "Blueprint is purely informational",
                "sprite info")

        return badges


class KarmaCategoryImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IKarmaCategory objects to an image.

    Used for image:icon.
    """

    icons_for_karma_categories = {
        'bugs': '/@@/bug',
        'code': '/@@/branch',
        'translations': '/@@/translation',
        'specs': '/@@/blueprint',
        'soyuz': '/@@/package-source',
        'answers': '/@@/question'}

    def icon(self):
        icon = self.icons_for_karma_categories[self._context.name]
        return ('<img height="14" width="14" alt="" title="%s" src="%s" />'
                % (self._context.title, icon))


class MilestoneImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IMilestone objects to an image.

    Used for image:icon.
    """

    def icon(self):
        """Return the appropriate <img> tag for the milestone icon."""
        return '<img height="14" width="14" alt="" src="/@@/milestone" />'


class BuildImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IBuild objects to an image.

    Used for image:icon.
    """
    icon_template = (
        '<img width="%(width)s" height="14" alt="%(alt)s" '
        'title="%(title)s" src="%(src)s" />')

    def icon(self):
        """Return the appropriate <img> tag for the build icon."""
        icon_map = {
            BuildStatus.NEEDSBUILD: {'src': "/@@/build-needed"},
            BuildStatus.FULLYBUILT: {'src': "/@@/build-success"},
            BuildStatus.FAILEDTOBUILD: {
                'src': "/@@/build-failed",
                'width': '16',
                },
            BuildStatus.MANUALDEPWAIT: {'src': "/@@/build-depwait"},
            BuildStatus.CHROOTWAIT: {'src': "/@@/build-chrootwait"},
            BuildStatus.SUPERSEDED: {'src': "/@@/build-superseded"},
            BuildStatus.BUILDING: {'src': "/@@/processing"},
            BuildStatus.UPLOADING: {'src': "/@@/processing"},
            BuildStatus.FAILEDTOUPLOAD: {'src': "/@@/build-failedtoupload"},
            BuildStatus.CANCELLING: {'src': "/@@/processing"},
            BuildStatus.CANCELLED: {'src': "/@@/build-failed"},
            }

        alt = '[%s]' % self._context.status.name
        title = self._context.status.title
        source = icon_map[self._context.status].get('src')
        width = icon_map[self._context.status].get('width', '14')

        return self.icon_template % {
            'alt': alt,
            'title': title,
            'src': source,
            'width': width,
            }


class ArchiveImageDisplayAPI(ObjectImageDisplayAPI):
    """Adapter for IArchive objects to an image.

    Used for image:icon.
    """
    icon_template = """
        <img width="14" height="14" alt="%s" title="%s" src="%s" />
        """

    def icon(self):
        """Return the appropriate <img> tag for an archive."""
        icon_map = {
            ArchivePurpose.PRIMARY: '/@@/distribution',
            ArchivePurpose.PARTNER: '/@@/distribution',
            ArchivePurpose.PPA: '/@@/ppa-icon',
            ArchivePurpose.COPY: '/@@/distribution',
            }

        alt = '[%s]' % self._context.purpose.title
        title = self._context.purpose.title
        source = icon_map[self._context.purpose]

        return self.icon_template % (alt, title, source)


class BadgeDisplayAPI:
    """Adapter for IHasBadges to the images for the badges.

    Used for context/badges:small and context/badges:large.
    """

    def __init__(self, context):
        # Adapt the context.
        self.context = IHasBadges(context)

    def small(self):
        """Render the visible badge's icon images."""
        badges = self.context.getVisibleBadges()
        return ''.join([badge.renderIconImage() for badge in badges])

    def large(self):
        """Render the visible badge's heading images."""
        badges = self.context.getVisibleBadges()
        return ''.join([badge.renderHeadingImage() for badge in badges])


class PersonFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IPerson` objects to a formatted string."""

    traversable_names = {'link': 'link', 'url': 'url', 'api_url': 'api_url',
                         'icon': 'icon',
                         'displayname': 'displayname',
                         'unique_displayname': 'unique_displayname',
                         'link-display-name-id': 'link_display_name_id',
                         }

    final_traversable_names = {'local-time': 'local_time'}
    final_traversable_names.update(ObjectFormatterAPI.final_traversable_names)

    def local_time(self):
        """Return the local time for this person."""
        time_zone = 'UTC'
        if self._context.time_zone is not None:
            time_zone = self._context.time_zone
        return datetime.now(pytz.timezone(time_zone)).strftime('%T %Z')

    def url(self, view_name=None, rootsite='mainsite'):
        """See `ObjectFormatterAPI`.

        The default URL for a person is to the mainsite.
        """
        return super(PersonFormatterAPI, self).url(view_name, rootsite)

    def _makeLink(self, view_name, rootsite, text):
        person = self._context
        url = self.url(view_name, rootsite)
        custom_icon = ObjectImageDisplayAPI(person).custom_icon_url()
        if custom_icon is None:
            css_class = ObjectImageDisplayAPI(person).sprite_css()
            return structured(
                '<a href="%s" class="%s">%s</a>',
                url, css_class, text).escapedtext
        else:
            return structured(
                '<a href="%s" class="bg-image" '
                'style="background-image: url(%s)">%s</a>',
                url, custom_icon, text).escapedtext

    def link(self, view_name, rootsite='mainsite'):
        """See `ObjectFormatterAPI`.

        Return an HTML link to the person's page containing an icon
        followed by the person's name. The default URL for a person is to
        the mainsite.
        """
        return self._makeLink(view_name, rootsite, self._context.displayname)

    def displayname(self, view_name, rootsite=None):
        """Return the displayname as a string."""
        person = self._context
        return person.displayname

    def unique_displayname(self, view_name):
        """Return the unique_displayname as a string."""
        person = self._context
        return person.unique_displayname

    def icon(self, view_name):
        """Return the URL for the person's icon."""
        custom_icon = ObjectImageDisplayAPI(
            self._context).custom_icon_url()
        if custom_icon is None:
            css_class = ObjectImageDisplayAPI(self._context).sprite_css()
            return '<span class="' + css_class + '"></span>'
        else:
            return '<img src="%s" width="14" height="14" />' % custom_icon

    def link_display_name_id(self, view_name):
        """Return a link to the user's profile page.

        The link text uses both the display name and Launchpad id to clearly
        indicate which user profile is linked.
        """
        text = self.unique_displayname(None)
        return self._makeLink(view_name, 'mainsite', text)


class MixedVisibilityError(Exception):
    """An informational error that visibility is being mixed."""


class TeamFormatterAPI(PersonFormatterAPI):
    """Adapter for `ITeam` objects to a formatted string."""

    hidden = u'<hidden>'

    def url(self, view_name=None, rootsite='mainsite'):
        """See `ObjectFormatterAPI`.

        The default URL for a team is to the mainsite. None is returned
        when the user does not have permission to review the team.
        """
        if not check_permission('launchpad.LimitedView', self._context):
            # This person has no permission to view the team details.
            self._report_visibility_leak()
            return None
        return super(TeamFormatterAPI, self).url(view_name, rootsite)

    def api_url(self, context):
        """See `ObjectFormatterAPI`."""
        if not check_permission('launchpad.LimitedView', self._context):
            # This person has no permission to view the team details.
            self._report_visibility_leak()
            return None
        return super(TeamFormatterAPI, self).api_url(context)

    def link(self, view_name, rootsite='mainsite'):
        """See `ObjectFormatterAPI`.

        The default URL for a team is to the mainsite. None is returned
        when the user does not have permission to review the team.
        """
        person = self._context
        if not check_permission('launchpad.LimitedView', person):
            # This person has no permission to view the team details.
            self._report_visibility_leak()
            return structured(
                '<span class="sprite team">%s</span>', self.hidden).escapedtext
        return super(TeamFormatterAPI, self).link(view_name, rootsite)

    def icon(self, view_name):
        team = self._context
        if not check_permission('launchpad.LimitedView', team):
            css_class = ObjectImageDisplayAPI(team).sprite_css()
            return '<span class="' + css_class + '"></span>'
        else:
            return super(TeamFormatterAPI, self).icon(view_name)

    def displayname(self, view_name, rootsite=None):
        """See `PersonFormatterAPI`."""
        person = self._context
        if not check_permission('launchpad.LimitedView', person):
            # This person has no permission to view the team details.
            self._report_visibility_leak()
            return self.hidden
        return super(TeamFormatterAPI, self).displayname(view_name, rootsite)

    def unique_displayname(self, view_name):
        """See `PersonFormatterAPI`."""
        person = self._context
        if not check_permission('launchpad.LimitedView', person):
            # This person has no permission to view the team details.
            self._report_visibility_leak()
            return self.hidden
        return super(TeamFormatterAPI, self).unique_displayname(view_name)

    def _report_visibility_leak(self):
        request = get_current_browser_request()
        try:
            raise MixedVisibilityError()
        except MixedVisibilityError:
            getUtility(IErrorReportingUtility).raising(
                sys.exc_info(), request)


class CustomizableFormatter(ObjectFormatterAPI):
    """A ObjectFormatterAPI that is easy to customize.

    This provides fmt:url and fmt:link support for the object it
    adapts.

    For most object types, only the _link_summary_template class
    variable and _link_summary_values method need to be overridden.
    This assumes that:

      1. canonical_url produces appropriate urls for this type,
      2. the launchpad.View permission alone is required to view this
         object's url, and,
      3. if there is an icon for this object type, image:icon is
         implemented and appropriate.

    For greater control over the summary, overrride
    _make_link_summary.

    If a different permission is required, override _link_permission.
    """

    _link_permission = 'launchpad.View'

    def _link_summary_values(self):
        """Return a dict of values to use for template substitution.

        These values should not be escaped, as this will be performed later.
        For this reason, only string values should be supplied.
        """
        raise NotImplementedError(self._link_summary_values)

    def _make_link_summary(self):
        """Create a summary from _template and _link_summary_values().

        This summary is for use in fmt:link, which is meant to be used in
        contexts like lists of items.
        """
        values = dict(
            (k, v if v is not None else '')
            for k, v in self._link_summary_values().iteritems())
        return structured(self._link_summary_template, **values).escapedtext

    def _title_values(self):
        """Return a dict of values to use for template substitution.

        These values should not be escaped, as this will be performed later.
        For this reason, only string values should be supplied.
        """
        return {}

    def _make_title(self):
        """Create a title from _title_template and _title_values().

        This title is for use in fmt:link, which is meant to be used in
        contexts like lists of items.
        """
        title_template = getattr(self, '_title_template', None)
        if title_template is None:
            return None
        values = dict(
            (k, v if v is not None else '')
            for k, v in self._title_values().iteritems())
        return structured(title_template, **values).escapedtext

    def sprite_css(self):
        """Retrieve the icon for the _context, if any.

        :return: The icon css or None if no icon is available.
        """
        return queryAdapter(self._context, IPathAdapter, 'image').sprite_css()

    def link(self, view_name, rootsite=None):
        """Return html including a link, description and icon.

        Icon and link are optional, depending on type and permissions.
        Uses self._make_link_summary for the summary, self._get_icon
        for the icon, self._should_link to determine whether to link, and
        self.url() to generate the url.
        """
        sprite = self.sprite_css()
        if sprite is None:
            css = ''
        else:
            css = ' class="' + sprite + '"'

        summary = self._make_link_summary()
        title = self._make_title()
        if title is None:
            title = ''
        else:
            title = ' title="%s"' % title

        if check_permission(self._link_permission, self._context):
            url = self.url(view_name, rootsite)
        else:
            url = ''
        if url:
            return '<a href="%s"%s%s>%s</a>' % (url, css, title, summary)
        else:
            return summary


class PillarFormatterAPI(CustomizableFormatter):
    """Adapter for IProduct, IDistribution and IProjectGroup objects to a
    formatted string."""

    _link_summary_template = '%(displayname)s'
    _link_permission = 'zope.Public'

    traversable_names = {
        'api_url': 'api_url',
        'link': 'link',
        'url': 'url',
        'link_with_displayname': 'link_with_displayname'
        }

    def _link_summary_values(self):
        displayname = self._context.displayname
        return {'displayname': displayname}

    def url(self, view_name=None, rootsite=None):
        """See `ObjectFormatterAPI`.

        The default URL for a pillar is to the mainsite.
        """
        return super(PillarFormatterAPI, self).url(view_name, rootsite)

    def _getLinkHTML(self, view_name, rootsite,
        template, custom_icon_template):
        """Generates html, mapping a link context to given templates.

        The html is generated using given `template` or `custom_icon_template`
        based on the presence of a custom icon for Products/ProjectGroups.
        Named string substitution is used to render the final html
        (see below for a list of allowed keys).

        The link context is a dict containing info about current
        Products or ProjectGroups.
        Keys are `url`, `name`, `displayname`, `custom_icon` (if present),
        `css_class` (if a custom icon does not exist),
        'summary' (see CustomizableFormatter._make_link_summary()).
        """
        context = self._context
        # XXX wgrant: the structured() in this dict is evil; refactor.
        mapping = {
            'url': self.url(view_name, rootsite),
            'name': context.name,
            'displayname': context.displayname,
            'summary': structured(self._make_link_summary()),
            }
        custom_icon = ObjectImageDisplayAPI(context).custom_icon_url()
        if custom_icon is None:
            mapping['css_class'] = ObjectImageDisplayAPI(context).sprite_css()
            return structured(template, **mapping).escapedtext
        mapping['custom_icon'] = custom_icon
        return structured(custom_icon_template, **mapping).escapedtext

    def link(self, view_name, rootsite='mainsite'):
        """The html to show a link to a Product, ProjectGroup or distribution.

        In the case of Products or ProjectGroups we display the custom
        icon, if one exists. The default URL for a pillar is to the mainsite.
        """
        super(PillarFormatterAPI, self).link(view_name)
        template = u'<a href="%(url)s" class="%(css_class)s">%(summary)s</a>'
        custom_icon_template = (
            u'<a href="%(url)s" class="bg-image" '
            u'style="background-image: url(%(custom_icon)s)">%(summary)s</a>'
            )
        return self._getLinkHTML(
            view_name, rootsite, template, custom_icon_template)

    def link_with_displayname(self, view_name, rootsite='mainsite'):
        """The html to show a link to a Product, ProjectGroup or
        distribution, including displayname and name.

        In the case of Products or ProjectGroups we display the custom
        icon, if one exists. The default URL for a pillar is to the mainsite.
        """
        super(PillarFormatterAPI, self).link(view_name)
        template = (
            u'<a href="%(url)s" class="%(css_class)s">%(displayname)s</a>'
            u'&nbsp;(<a href="%(url)s">%(name)s</a>)'
            )
        custom_icon_template = (
            u'<a href="%(url)s" class="bg-image" '
            u'style="background-image: url(%(custom_icon)s)">'
            u'%(displayname)s</a>&nbsp;(<a href="%(url)s">%(name)s</a>)'
            )
        return self._getLinkHTML(
            view_name, rootsite, template, custom_icon_template)


class DistroSeriesFormatterAPI(CustomizableFormatter):
    """Adapter for IDistroSeries objects to a formatted string."""

    _link_summary_template = '%(displayname)s'
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        displayname = self._context.displayname
        return {'displayname': displayname}


class SourcePackageReleaseFormatterAPI(CustomizableFormatter):

    """Adapter for ISourcePackageRelease objects to a formatted string."""

    _link_summary_template = '%(sourcepackage)s %(version)s'

    def _link_summary_values(self):
        return {'sourcepackage':
                self._context.distrosourcepackage.displayname,
                'version': self._context.version}


class ProductReleaseFileFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IProductReleaseFile` objects to a formatted string."""

    traversable_names = {'link': 'link', 'url': 'url'}

    def link(self, view_name):
        """A hyperlinked ProductReleaseFile.

        This consists of a download icon, the link to the ProductReleaseFile
        itself (with a tooltip stating its size) and links to that file's
        signature and MD5 hash.
        """
        file_ = self._context
        file_size = NumberFormatterAPI(
            file_.libraryfile.content.filesize).bytes()
        if file_.description is not None:
            description = file_.description
        else:
            description = file_.libraryfile.filename
        link_title = "%s (%s)" % (description, file_size)
        download_url = self._getDownloadURL(file_.libraryfile)
        md5_url = urlappend(download_url, '+md5')
        replacements = dict(
            url=download_url, filename=file_.libraryfile.filename,
            md5_url=md5_url, link_title=link_title)
        html = (
            '<img alt="download icon" src="/@@/download" />'
            '<strong>'
            '  <a title="%(link_title)s" href="%(url)s">%(filename)s</a> '
            '</strong>'
            '(<a href="%(md5_url)s">md5</a>')
        if file_.signature is not None:
            html += ', <a href="%(signature_url)s">sig</a>)'
            replacements['signature_url'] = self._getDownloadURL(
                file_.signature)
        else:
            html += ')'
        return structured(html, **replacements).escapedtext

    def url(self, view_name=None, rootsite=None):
        """Return the URL to download the file."""
        return self._getDownloadURL(self._context.libraryfile)

    @property
    def _release(self):
        return self._context.productrelease

    def _getDownloadURL(self, lfa):
        """Return the download URL for the given `LibraryFileAlias`."""
        url = urlappend(canonical_url(self._release), '+download')
        # Quote the filename to eliminate non-ascii characters which
        # are invalid in the url.
        return urlappend(url, urllib.quote(lfa.filename.encode('utf-8')))


class BranchFormatterAPI(ObjectFormatterAPI):
    """Adapter for IBranch objects to a formatted string."""

    traversable_names = {
        'link': 'link', 'url': 'url',
        'title-link': 'titleLink', 'bzr-link': 'bzrLink',
        'api_url': 'api_url'}

    def _args(self, view_name):
        """Generate a dict of attributes for string template expansion."""
        branch = self._context
        return {
            'bzr_identity': branch.bzr_identity,
            'display_name': branch.displayname,
            'name': branch.name,
            'unique_name': branch.unique_name,
            'url': self.url(view_name),
            }

    def link(self, view_name):
        """A hyperlinked branch icon with the displayname."""
        return structured(
            '<a href="%(url)s" class="sprite branch">'
            '%(display_name)s</a>', **self._args(view_name)).escapedtext

    def bzrLink(self, view_name):
        """A hyperlinked branch icon with the bazaar identity."""
        # Defer to link.
        return self.link(view_name)

    def titleLink(self, view_name):
        """A hyperlinked branch name with following title."""
        return structured(
            '<a href="%(url)s" title="%(display_name)s">'
            '%(name)s</a>: %(title)s', **self._args(view_name)).escapedtext


class BranchSubscriptionFormatterAPI(CustomizableFormatter):
    """Adapter for IBranchSubscription objects to a formatted string."""

    _link_summary_template = _('Subscription of %(person)s to %(branch)s')

    def _link_summary_values(self):
        """Provide values for template substitution"""
        return {
            'person': self._context.person.displayname,
            'branch': self._context.branch.displayname,
        }


class BranchMergeProposalFormatterAPI(CustomizableFormatter):

    _link_summary_template = _('%(title)s')

    def _link_summary_values(self):
        return {
            'title': self._context.title,
            }


class BugBranchFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for BugBranch objects"""

    def _get_task_formatter(self):
        task = self._context.bug.getBugTask(self._context.branch.product)
        if task is None:
            task = self._context.bug.bugtasks[0]
        return BugTaskFormatterAPI(task)

    def _make_link_summary(self):
        """Return the summary of the related product's bug task"""
        return self._get_task_formatter()._make_link_summary()

    def _get_icon(self):
        """Return the icon of the related product's bugtask"""
        return self._get_task_formatter()._get_icon()


class BugFormatterAPI(CustomizableFormatter):
    """Adapter for IBug objects to a formatted string."""

    _link_summary_template = 'Bug #%(id)s: %(title)s'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'id': str(self._context.id), 'title': self._context.title}


class BugTaskFormatterAPI(CustomizableFormatter):
    """Adapter for IBugTask objects to a formatted string."""

    _title_template = '%(importance)s - %(status)s'

    def _title_values(self):
        return {'importance': self._context.importance.title,
                'status': self._context.status.title}

    def _make_link_summary(self):
        return BugFormatterAPI(self._context.bug)._make_link_summary()


class CodeImportFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for CodeImport objects"""

    _link_summary_template = _('Import of %(target)s: %(branch)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'target': self._context.branch.target.displayname,
                'branch': self._context.branch.bzr_identity,
               }

    def url(self, view_name=None, rootsite=None):
        """See `ObjectFormatterAPI`."""
        # The url of a code import is the associated branch.
        # This is still here primarily for supporting branch deletion,
        # which does a fmt:link of the other entities that will be deleted.
        url = canonical_url(
            self._context.branch, path_only_if_possible=True,
            view_name=view_name)
        return url


class PackageBuildFormatterAPI(ObjectFormatterAPI):
    """Adapter providing fmt support for `IPackageBuild` objects."""

    def _composeArchiveReference(self, archive):
        if archive.is_ppa:
            return " [%s/%s]" % (archive.owner.name, archive.name)
        else:
            return ""

    def link(self, view_name, rootsite=None):
        build = self._context
        if (not check_permission('launchpad.View', build) or
            not check_permission('launchpad.View', build.archive.owner)):
            return 'private job'

        url = self.url(view_name=view_name, rootsite=rootsite)
        archive = self._composeArchiveReference(build.archive)
        return structured(
            '<a href="%s">%s</a>%s', url, build.title, archive).escapedtext


class CodeImportMachineFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for CodeImport objects"""

    _link_summary_template = _('%(hostname)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'hostname': self._context.hostname}


class MilestoneFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for Milestone objects."""

    _link_summary_template = _('%(title)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'title': self._context.title}


class ProductReleaseFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for Milestone objects."""

    _link_summary_template = _('%(displayname)s %(code_name)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        code_name = self._context.milestone.code_name
        if code_name is None or code_name.strip() == '':
            code_name = ''
        else:
            code_name = '(%s)' % code_name.strip()
        return dict(displayname=self._context.milestone.displayname,
                    code_name=code_name)


class ProductSeriesFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for ProductSeries objects"""

    _link_summary_template = _('%(product)s %(series)s series')

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'series': self._context.name,
                'product': self._context.product.displayname}


class QuestionFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for question objects."""

    _link_summary_template = _('%(id)s: %(title)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'id': str(self._context.id), 'title': self._context.title}


class SourcePackageRecipeFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for ISourcePackageRecipe objects."""

    _link_summary_template = 'Recipe %(name)s for %(owner)s'

    def _link_summary_values(self):
        return {'name': self._context.name,
                'owner': self._context.owner.displayname}


class SpecificationFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for Specification objects"""

    _link_summary_template = _('%(title)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'title': self._context.title}


class CodeReviewCommentFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for CodeReviewComment objects"""

    _link_summary_template = _('Comment by %(author)s')
    _link_permission = 'zope.Public'

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'author': self._context.message.owner.displayname}


class ArchiveFormatterAPI(CustomizableFormatter):
    """Adapter providing fmt support for `IArchive` objects."""

    _link_summary_template = '%(display_name)s'
    _link_permission = 'launchpad.View'
    _reference_permission = 'launchpad.SubscriberView'
    _reference_template = "ppa:%(owner_name)s/%(ppa_name)s"

    final_traversable_names = {'reference': 'reference'}
    final_traversable_names.update(
        CustomizableFormatter.final_traversable_names)

    def _link_summary_values(self):
        """See CustomizableFormatter._link_summary_values."""
        return {'display_name': self._context.displayname}

    def link(self, view_name):
        """Return html including a link for the context archive.

        Render a link using CSS sprites for users with permission to view
        the archive.

        Disabled PPAs are listed with sprites but not linkified.

        Inaccessible private PPAs are not rendered at all (empty string
        is returned).
        """
        summary = self._make_link_summary()
        css = self.sprite_css()
        if check_permission(self._link_permission, self._context):
            if self._context.is_main:
                url = queryAdapter(
                    self._context.distribution, IPathAdapter, 'fmt').url(
                        view_name)
            else:
                url = self.url(view_name)
            return '<a href="%s" class="%s">%s</a>' % (url, css, summary)
        else:
            if not self._context.private:
                return '<span class="%s">%s</span>' % (css, summary)
            else:
                return ''

    def reference(self, view_name=None, rootsite=None):
        """Return the text PPA reference for a PPA."""
        if not IPPA.providedBy(self._context):
            raise NotImplementedError(
                "No reference implementation for non-PPA archive %r." %
                self._context)
        if not check_permission(self._reference_permission, self._context):
            return ''
        return self._reference_template % {
            'owner_name': self._context.owner.name,
            'ppa_name': self._context.name}


class SpecificationBranchFormatterAPI(CustomizableFormatter):
    """Adapter for ISpecificationBranch objects to a formatted string."""

    def _make_link_summary(self):
        """Provide the summary of the linked spec"""
        formatter = SpecificationFormatterAPI(self._context.specification)
        return formatter._make_link_summary()

    def _get_icon(self):
        """Provide the icon of the linked spec"""
        formatter = SpecificationFormatterAPI(self._context.specification)
        return formatter._get_icon()

    def sprite_css(self):
        return queryAdapter(
            self._context.specification, IPathAdapter, 'image').sprite_css()


class BugTrackerFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IBugTracker` objects to a formatted string."""

    final_traversable_names = {
        'aliases': 'aliases',
        'external-link': 'external_link',
        'external-title-link': 'external_title_link'}
    final_traversable_names.update(ObjectFormatterAPI.final_traversable_names)

    def link(self, view_name):
        """Return an HTML link to the bugtracker page.

        If the user is not logged-in, the title of the bug tracker is
        modified to obfuscate all email addresses.
        """
        url = self.url(view_name)
        title = self._context.title
        if getUtility(ILaunchBag).user is None:
            title = FormattersAPI(title).obfuscate_email()
        return structured('<a href="%s">%s</a>', url, title).escapedtext

    def external_link(self):
        """Return an HTML link to the external bugtracker.

        If the user is not logged-in, and the URL of the bugtracker
        contains an email address, this returns the obfuscated URL as
        text (i.e. no <a/> link).
        """
        url = self._context.baseurl
        if url.startswith('mailto:') and getUtility(ILaunchBag).user is None:
            return html_escape(u'mailto:<email address hidden>')
        else:
            return structured(
                '<a class="link-external" href="%(url)s">%(url)s</a>',
                url=url).escapedtext

    def external_title_link(self):
        """Return an HTML link to the external bugtracker.

        If the user is not logged-in, the title of the bug tracker is
        modified to obfuscate all email addresses. Additonally, if the
        URL is a mailto: address then no link is returned, just the
        title text.
        """
        url = self._context.baseurl
        title = self._context.title
        if getUtility(ILaunchBag).user is None:
            title = FormattersAPI(title).obfuscate_email()
            if url.startswith('mailto:'):
                return html_escape(title)
        return structured(
            '<a class="link-external" href="%s">%s</a>',
            url, title).escapedtext

    def aliases(self):
        """Generate alias URLs, obfuscating where necessary.

        If the user is not logged-in, email addresses should be
        hidden.
        """
        anonymous = getUtility(ILaunchBag).user is None
        for alias in self._context.aliases:
            if anonymous and alias.startswith('mailto:'):
                yield u'mailto:<email address hidden>'
            else:
                yield alias


class BugWatchFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IBugWatch` objects to a formatted string."""

    final_traversable_names = {
        'external-link': 'external_link',
        'external-link-short': 'external_link_short'}
    final_traversable_names.update(ObjectFormatterAPI.final_traversable_names)

    def _make_external_link(self, summary=None):
        """Return an external HTML link to the target of the bug watch.

        If a summary is not specified or empty, an em-dash is used as
        the content of the link.

        If the user is not logged in and the URL of the bug watch is
        an email address, only the summary is returned (i.e. no link).
        """
        if summary is None or len(summary) == 0:
            summary = structured(u'&mdash;')
        url = self._context.url
        if url.startswith('mailto:') and getUtility(ILaunchBag).user is None:
            return html_escape(summary)
        else:
            return structured(
                '<a class="link-external" href="%s">%s</a>',
                url, summary).escapedtext

    def external_link(self):
        """Return an HTML link with a detailed link text.

        The link text is formed from the bug tracker name and the
        remote bug number.
        """
        summary = self._context.bugtracker.name
        remotebug = self._context.remotebug
        if remotebug is not None and len(remotebug) > 0:
            summary = u'%s #%s' % (summary, remotebug)
        return self._make_external_link(summary)

    def external_link_short(self):
        """Return an HTML link with a short link text.

        The link text is formed from the bug tracker name and the
        remote bug number.
        """
        return self._make_external_link(self._context.remotebug)


class NumberFormatterAPI:
    """Adapter for converting numbers to formatted strings."""

    implements(ITraversable)

    def __init__(self, number):
        self._number = number

    def traverse(self, name, furtherPath):
        if name == 'float':
            if len(furtherPath) != 1:
                raise TraversalError(
                    "fmt:float requires a single decimal argument")
            # coerce the argument to float to ensure it's safe
            format = furtherPath.pop()
            return self.float(float(format))
        elif name == 'bytes':
            return self.bytes()
        elif name == 'intcomma':
            return self.intcomma()
        else:
            raise TraversalError(name)

    def intcomma(self):
        """Return this number with its thousands separated by comma.

        This can only be used for integers.
        """
        if not isinstance(self._number, int):
            raise AssertionError("This can't be used with non-integers")
        L = []
        for index, char in enumerate(reversed(str(self._number))):
            if index != 0 and (index % 3) == 0:
                L.insert(0, ',')
            L.insert(0, char)
        return ''.join(L)

    def bytes(self):
        """Render number as byte contractions according to IEC60027-2."""
        # See http://en.wikipedia.org/wiki
        # /Binary_prefixes#Specific_units_of_IEC_60027-2_A.2
        assert not float(self._number) < 0, "Expected a non-negative number."
        n = int(self._number)
        if n == 1:
            # Handle the singular case.
            return "1 byte"
        if n == 0:
            # To avoid math.log(0, X) blowing up.
            return "0 bytes"
        suffixes = ["KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
        exponent = int(math.log(n, 1024))
        exponent = min(len(suffixes), exponent)
        if exponent < 1:
            # If this is less than 1 KiB, no need for rounding.
            return "%s bytes" % n
        return "%.1f %s" % (n / 1024.0 ** exponent, suffixes[exponent - 1])

    def float(self, format):
        """Use like tal:content="context/foo/fmt:float/.2".

        Will return a string formatted to the specification provided in
        the manner Python "%f" formatter works. See
        http://docs.python.org/lib/typesseq-strings.html for details and
        doc.displaying-numbers for various examples.
        """
        value = "%" + str(format) + "f"
        return value % float(self._number)


class DateTimeFormatterAPI:
    """Adapter from datetime objects to a formatted string."""

    def __init__(self, datetimeobject):
        self._datetime = datetimeobject

    def time(self):
        if self._datetime.tzinfo:
            value = self._datetime.astimezone(
                getUtility(ILaunchBag).time_zone)
            return value.strftime('%T %Z')
        else:
            return self._datetime.strftime('%T')

    def date(self):
        value = self._datetime
        if value.tzinfo:
            value = value.astimezone(
                getUtility(ILaunchBag).time_zone)
        return value.strftime('%Y-%m-%d')

    def _now(self):
        # This method exists to be overridden in tests.
        if self._datetime.tzinfo:
            # datetime is offset-aware
            return datetime.now(pytz.timezone('UTC'))
        else:
            # datetime is offset-naive
            return datetime.utcnow()

    def displaydate(self):
        delta = abs(self._now() - self._datetime)
        if delta > timedelta(1, 0, 0):
            # far in the past or future, display the date
            return 'on ' + self.date()
        return self.approximatedate()

    def approximatedate(self):
        delta = self._now() - self._datetime
        if abs(delta) > timedelta(1, 0, 0):
            # far in the past or future, display the date
            return self.date()
        future = delta < timedelta(0, 0, 0)
        delta = abs(delta)
        days = delta.days
        hours = delta.seconds / 3600
        minutes = (delta.seconds - (3600 * hours)) / 60
        seconds = delta.seconds % 60
        result = ''
        if future:
            result += 'in '
        if days != 0:
            amount = days
            unit = 'day'
        elif hours != 0:
            amount = hours
            unit = 'hour'
        elif minutes != 0:
            amount = minutes
            unit = 'minute'
        else:
            if seconds <= 10:
                result += 'a moment'
                if not future:
                    result += ' ago'
                return result
            else:
                amount = seconds
                unit = 'second'
        if amount != 1:
            unit += 's'
        result += '%s %s' % (amount, unit)
        if not future:
            result += ' ago'
        return result

    def datetime(self):
        return "%s %s" % (self.date(), self.time())

    def rfc822utcdatetime(self):
        return formatdate(
            rfc822.mktime_tz(self._datetime.utctimetuple() + (0, )))

    def isodate(self):
        return self._datetime.isoformat()

    @staticmethod
    def _yearDelta(old, new):
        """Return the difference in years between two datetimes.

        :param old: The old date
        :param new: The new date
        """
        year_delta = new.year - old.year
        year_timedelta = datetime(new.year, 1, 1) - datetime(old.year, 1, 1)
        if new - old < year_timedelta:
            year_delta -= 1
        return year_delta

    def durationsince(self):
        """How long since the datetime, as a string."""
        now = self._now()
        number = self._yearDelta(self._datetime, now)
        unit = 'year'
        if number < 1:
            delta = now - self._datetime
            if delta.days > 0:
                number = delta.days
                unit = 'day'
            else:
                number = delta.seconds / 60
                if number == 0:
                    return 'less than a minute'
                unit = 'minute'
                if number >= 60:
                    number /= 60
                    unit = 'hour'
        if number != 1:
            unit += 's'
        return '%d %s' % (number, unit)


class SeriesSourcePackageBranchFormatter(ObjectFormatterAPI):
    """Formatter for a SourcePackage, Pocket -> Branch link.

    Since the link object is never really interesting in and of itself, we
    always link to the source package instead.
    """

    def url(self, view_name=None, rootsite=None):
        return queryAdapter(
            self._context.sourcepackage, IPathAdapter, 'fmt').url(
                view_name, rootsite)

    def link(self, view_name):
        return queryAdapter(
            self._context.sourcepackage, IPathAdapter, 'fmt').link(view_name)


class DurationFormatterAPI:
    """Adapter from timedelta objects to a formatted string."""

    implements(ITraversable)

    def __init__(self, duration):
        self._duration = duration

    def traverse(self, name, furtherPath):
        if name == 'exactduration':
            return self.exactduration()
        elif name == 'approximateduration':
            return self.approximateduration()
        elif name == 'millisecondduration':
            return self.millisecondduration()
        else:
            raise TraversalError(name)

    def exactduration(self):
        """Format timedeltas as "v days, w hours, x minutes, y.z seconds"."""
        parts = []
        minutes, seconds = divmod(self._duration.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        seconds = seconds + (float(self._duration.microseconds) / 10 ** 6)
        if self._duration.days > 0:
            if self._duration.days == 1:
                parts.append('%d day' % self._duration.days)
            else:
                parts.append('%d days' % self._duration.days)
        if parts or hours > 0:
            if hours == 1:
                parts.append('%d hour' % hours)
            else:
                parts.append('%d hours' % hours)
        if parts or minutes > 0:
            if minutes == 1:
                parts.append('%d minute' % minutes)
            else:
                parts.append('%d minutes' % minutes)
        if parts or seconds > 0:
            parts.append('%0.1f seconds' % seconds)

        return ', '.join(parts)

    def approximateduration(self):
        """Return a nicely-formatted approximate duration.

        E.g. '1 hour', '3 minutes', '1 hour 10 minutes' and so forth.

        See https://launchpad.canonical.com/PresentingLengthsOfTime.
        """
        # NOTE: There are quite a few "magic numbers" in this
        # implementation; they are generally just figures pulled
        # directly out of the PresentingLengthsOfTime spec, and so
        # it's not particularly easy to give each and every number of
        # a useful name. It's also unlikely that these numbers will be
        # changed.

        seconds = total_seconds(self._duration)

        # First we'll try to calculate an approximate number of
        # seconds up to a minute. We'll start by defining a sorted
        # list of (boundary, display value) tuples.  We want to show
        # the display value corresponding to the lowest boundary that
        # 'seconds' is less than, if one exists.
        representation_in_seconds = [
            (1.5, '1 second'),
            (2.5, '2 seconds'),
            (3.5, '3 seconds'),
            (4.5, '4 seconds'),
            (7.5, '5 seconds'),
            (12.5, '10 seconds'),
            (17.5, '15 seconds'),
            (22.5, '20 seconds'),
            (27.5, '25 seconds'),
            (35, '30 seconds'),
            (45, '40 seconds'),
            (55, '50 seconds'),
            (90, '1 minute'),
        ]

        # Break representation_in_seconds into two pieces, to simplify
        # finding the correct display value, through the use of the
        # built-in bisect module.
        second_boundaries, display_values = zip(*representation_in_seconds)

        # Is seconds small enough that we can produce a representation
        # in seconds (up to '1 minute'?)
        if seconds < second_boundaries[-1]:
            # Use the built-in bisection algorithm to locate the index
            # of the item which "seconds" sorts after.
            matching_element_index = bisect(second_boundaries, seconds)

            # Return the corresponding display value.
            return display_values[matching_element_index]

        # Convert seconds into minutes, and round it.
        minutes, remaining_seconds = divmod(seconds, 60)
        minutes += remaining_seconds / 60.0
        minutes = int(round(minutes))

        if minutes <= 59:
            return "%d minutes" % minutes

        # Is the duration less than an hour and 5 minutes?
        if seconds < (60 + 5) * 60:
            return "1 hour"

        # Next phase: try and calculate an approximate duration
        # greater than one hour, but fewer than ten hours, to a 10
        # minute granularity.
        hours, remaining_seconds = divmod(seconds, 3600)
        ten_minute_chunks = int(round(remaining_seconds / 600.0))
        minutes = ten_minute_chunks * 10
        hours += (minutes / 60)
        minutes %= 60
        if hours < 10:
            if minutes:
                # If there is a minutes portion to display, the number
                # of hours is always shown as a digit.
                if hours == 1:
                    return "1 hour %s minutes" % minutes
                else:
                    return "%d hours %s minutes" % (hours, minutes)
            else:
                return "%d hours" % hours

        # Is the duration less than ten and a half hours?
        if seconds < (10.5 * 3600):
            return '10 hours'

        # Try to calculate the approximate number of hours, to a
        # maximum of 47.
        hours = int(round(seconds / 3600.0))
        if hours <= 47:
            return "%d hours" % hours

        # Is the duration fewer than two and a half days?
        if seconds < (2.5 * 24 * 3600):
            return '2 days'

        # Try to approximate to day granularity, up to a maximum of 13
        # days.
        days = int(round(seconds / (24 * 3600)))
        if days <= 13:
            return "%s days" % days

        # Is the duration fewer than two and a half weeks?
        if seconds < (2.5 * 7 * 24 * 3600):
            return '2 weeks'

        # If we've made it this far, we'll calculate the duration to a
        # granularity of weeks, once and for all.
        weeks = int(round(seconds / (7 * 24 * 3600.0)))
        return "%d weeks" % weeks

    def millisecondduration(self):
        return '%sms' % (total_seconds(self._duration) * 1000,)


class LinkFormatterAPI(ObjectFormatterAPI):
    """Adapter from Link objects to a formatted anchor."""
    final_traversable_names = {
        'icon': 'icon',
        'icon-link': 'link',
        'link-icon': 'link',
        }
    final_traversable_names.update(ObjectFormatterAPI.final_traversable_names)

    def icon(self):
        """Return the icon representation of the link."""
        request = get_current_browser_request()
        return getMultiAdapter(
            (self._context, request), name="+inline-icon")()

    def link(self, view_name=None, rootsite=None):
        """Return the default representation of the link."""
        return self._context.render()

    def url(self, view_name=None, rootsite=None):
        """Return the URL representation of the link."""
        if self._context.enabled:
            return self._context.url
        else:
            return u''


class RevisionAuthorFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IRevisionAuthor` links."""

    traversable_names = {'link': 'link'}

    def link(self, view_name=None, rootsite='mainsite'):
        """See `ObjectFormatterAPI`."""
        context = self._context
        if context.person is not None:
            return PersonFormatterAPI(self._context.person).link(
                view_name, rootsite)
        elif context.name_without_email:
            return html_escape(context.name_without_email)
        elif context.email and getUtility(ILaunchBag).user is not None:
            return html_escape(context.email)
        elif context.email:
            return html_escape("<email address hidden>")
        else:
            # The RevisionAuthor name and email is None.
            return ''


def clean_path_segments(request):
    """Returns list of path segments, excluding system-related segments."""
    proto_host_port = request.getApplicationURL()
    clean_url = request.getURL()
    clean_path = clean_url[len(proto_host_port):]
    clean_path_split = clean_path.split('/')
    return clean_path_split


class PermissionRequiredQuery:
    """Check if the logged in user has a given permission on a given object.

    Example usage::
        tal:condition="person/required:launchpad.Edit"
    """

    implements(ITraversable)

    def __init__(self, context):
        self.context = context

    def traverse(self, name, furtherPath):
        if len(furtherPath) > 0:
            raise TraversalError(
                    "There should be no further path segments after "
                    "required:permission")
        return check_permission(name, self.context)


class IMainTemplateFile(Interface):
    path = TextLine(title=u'The absolute path to this main template.')


class LaunchpadLayerToMainTemplateAdapter:
    adapts(LaunchpadLayer)
    implements(IMainTemplateFile)

    def __init__(self, context):
        here = os.path.dirname(os.path.realpath(__file__))
        self.path = os.path.join(here, '../templates/base-layout.pt')


class PageMacroDispatcher:
    """Selects a macro, while storing information about page layout.

        view/macro:page
        view/macro:page/main_side
        view/macro:page/main_only
        view/macro:page/searchless

        view/macro:pagehas/applicationtabs
        view/macro:pagehas/globalsearch
        view/macro:pagehas/portlets
        view/macro:pagehas/main

        view/macro:pagetype

        view/macro:is-page-contentless
        view/macro:has-watermark
    """

    implements(ITraversable)

    def __init__(self, context):
        # The context of this object is a view object.
        self.context = context

    @property
    def base(self):
        return ViewPageTemplateFile(
            IMainTemplateFile(self.context.request).path)

    def traverse(self, name, furtherPath):
        if name == 'page':
            if len(furtherPath) == 1:
                pagetype = furtherPath.pop()
            elif not furtherPath:
                pagetype = 'default'
            else:
                raise TraversalError("Max one path segment after macro:page")

            return self.page(pagetype)
        elif name == 'pagehas':
            if len(furtherPath) != 1:
                raise TraversalError(
                    "Exactly one path segment after macro:haspage")

            layoutelement = furtherPath.pop()
            return self.haspage(layoutelement)
        elif name == 'pagetype':
            return self.pagetype()
        elif name == 'is-page-contentless':
            return self.isPageContentless()
        elif name == 'has-watermark':
            return self.hasWatermark()
        else:
            raise TraversalError(name)

    def page(self, pagetype):
        if pagetype not in self._pagetypes:
            raise TraversalError('unknown pagetype: %s' % pagetype)
        self.context.__pagetype__ = pagetype
        return self.base.macros['master']

    def haspage(self, layoutelement):
        pagetype = getattr(self.context, '__pagetype__', None)
        if pagetype is None:
            pagetype = 'unset'
        return self._pagetypes[pagetype][layoutelement]

    def hasWatermark(self):
        """Does the page havethe watermark block.

        The default value is True, but the view can provide has_watermark
        to force the page not render the standard location information.
        """
        return getattr(self.context, 'has_watermark', True)

    def isPageContentless(self):
        """Should the template avoid rendering detailed information.

        Circumstances such as not possessing launchpad.View on a private
        context require the template to not render detailed information. The
        user may only know identifying information about the context.
        """
        view_context = self.context.context
        privacy = IPrivacy(view_context, None)
        if privacy is None or not privacy.private:
            return False
        return not (
            check_permission('launchpad.SubscriberView', view_context) or
            check_permission('launchpad.View', view_context))

    def pagetype(self):
        return getattr(self.context, '__pagetype__', 'unset')

    class LayoutElements:

        def __init__(self,
            applicationtabs=False,
            globalsearch=False,
            portlets=False,
            pagetypewasset=True,
            ):
            self.elements = vars()

        def __getitem__(self, name):
            return self.elements[name]

    _pagetypes = {
       'main_side':
            LayoutElements(
                applicationtabs=True,
                globalsearch=True,
                portlets=True),
       'main_only':
            LayoutElements(
                applicationtabs=True,
                globalsearch=True,
                portlets=False),
       'searchless':
            LayoutElements(
                applicationtabs=True,
                globalsearch=False,
                portlets=False),
        }


class TranslationGroupFormatterAPI(ObjectFormatterAPI):
    """Adapter for `ITranslationGroup` objects to a formatted string."""

    traversable_names = {
        'link': 'link',
        'url': 'url',
        'displayname': 'displayname',
    }

    def url(self, view_name=None, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        return super(TranslationGroupFormatterAPI, self).url(
            view_name, rootsite)

    def link(self, view_name, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        group = self._context
        url = self.url(view_name, rootsite)
        return structured('<a href="%s">%s</a>', url, group.title).escapedtext

    def displayname(self, view_name, rootsite=None):
        """Return the displayname as a string."""
        return self._context.title


class LanguageFormatterAPI(ObjectFormatterAPI):
    """Adapter for `ILanguage` objects to a formatted string."""
    traversable_names = {
        'link': 'link',
        'url': 'url',
        'displayname': 'displayname',
    }

    def url(self, view_name=None, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        return super(LanguageFormatterAPI, self).url(view_name, rootsite)

    def link(self, view_name, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        url = self.url(view_name, rootsite)
        return structured(
            '<a href="%s" class="sprite language">%s</a>',
            url, self._context.englishname).escapedtext

    def displayname(self, view_name, rootsite=None):
        """See `ObjectFormatterAPI`."""
        return self._context.englishname


class POFileFormatterAPI(ObjectFormatterAPI):
    """Adapter for `IPOFile` objects to a formatted string."""

    traversable_names = {
        'link': 'link',
        'url': 'url',
        'displayname': 'displayname',
    }

    def url(self, view_name=None, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        return super(POFileFormatterAPI, self).url(view_name, rootsite)

    def link(self, view_name, rootsite='translations'):
        """See `ObjectFormatterAPI`."""
        pofile = self._context
        url = self.url(view_name, rootsite)
        return structured('<a href="%s">%s</a>', url, pofile.title).escapedtext

    def displayname(self, view_name, rootsite=None):
        """Return the displayname as a string."""
        return self._context.title


def download_link(url, description, file_size):
    """Return HTML for downloading an item."""
    file_size = NumberFormatterAPI(file_size).bytes()
    formatted = structured(
        '<a href="%s">%s</a> (%s)', url, description, file_size)
    return formatted.escapedtext


class PackageDiffFormatterAPI(ObjectFormatterAPI):

    def link(self, view_name, rootsite=None):
        diff = self._context
        if not diff.date_fulfilled:
            return structured('%s (pending)', diff.title).escapedtext
        else:
            return download_link(
                diff.diff_content.http_url, diff.title,
                diff.diff_content.content.filesize)


class CSSFormatter:
    """A tales path adapter used for CSS rules.

    Using an expression like this:
        value/css:select/visible/hidden
    You will get "visible" if value evaluates to true, and "hidden" if the
    value evaluates to false.
    """

    implements(ITraversable)

    def __init__(self, context):
        self.context = context

    def select(self, furtherPath):
        if len(furtherPath) < 2:
            raise TraversalError('select needs two subsequent path elements.')
        true_value = furtherPath.pop()
        false_value = furtherPath.pop()
        if self.context:
            return true_value
        else:
            return false_value

    def traverse(self, name, furtherPath):
        try:
            return getattr(self, name)(furtherPath)
        except AttributeError:
            raise TraversalError(name)


class IRCNicknameFormatterAPI(ObjectFormatterAPI):
    """Adapter from IrcID objects to a formatted string."""

    implements(ITraversable)

    traversable_names = {
        'displayname': 'displayname',
        'formatted_displayname': 'formatted_displayname',
    }

    def displayname(self, view_name=None):
        return "%s on %s" % (self._context.nickname, self._context.network)

    def formatted_displayname(self, view_name=None):
        return structured(
            dedent("""\
                <strong>%s</strong>
                <span class="lesser"> on </span>
                <strong>%s</strong>
            """),
            self._context.nickname, self._context.network).escapedtext
