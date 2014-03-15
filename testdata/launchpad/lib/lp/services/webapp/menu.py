# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Menus and facets."""

__metaclass__ = type
__all__ = [
    'enabled_with_permission',
    'get_current_view',
    'get_facet',
    'FacetMenu',
    'ApplicationMenu',
    'ContextMenu',
    'NavigationMenu',
    'Link',
    'LinkData',
    'FacetLink',
    'MenuLink',
    ]

import types

from lazr.delegates import delegates
from lazr.restful.utils import get_current_browser_request
from lazr.uri import (
    InvalidURIError,
    URI,
    )
from zope.component import getMultiAdapter
from zope.interface import implements
from zope.security.proxy import (
    isinstance as zope_isinstance,
    removeSecurityProxy,
    )

from lp.services.webapp.escaping import html_escape
from lp.services.webapp.interfaces import (
    IApplicationMenu,
    IContextMenu,
    IFacetLink,
    IFacetMenu,
    ILink,
    ILinkData,
    IMenuBase,
    INavigationMenu,
    )
from lp.services.webapp.publisher import (
    canonical_url,
    LaunchpadView,
    UserAttributeCache,
    )
from lp.services.webapp.vhosts import allvhosts


def get_current_view(request=None):
    """Return the current view or None.

    :param request: A `IHTTPApplicationRequest`. If request is None, the
        current browser request is used.
    :return: The view from requests that provide IHTTPApplicationRequest.
    """
    request = request or get_current_browser_request()
    if request is None:
        return
    # The view is not in the list of traversed_objects, though it is listed
    # among the traversed_names. We need to get it from a private attribute.
    view = request._last_obj_traversed
    # Note: The last traversed object may be a view's instance method.
    bare = removeSecurityProxy(view)
    if zope_isinstance(view, types.MethodType):
        return bare.im_self
    return bare


def get_facet(view):
    """Return the view's facet name."""
    return getattr(removeSecurityProxy(view), '__launchpad_facetname__', None)


class LinkData:
    """General links that aren't default links.

    Instances of this class just provide link data.  The class is also known
    as 'Link' to make it nice to use when defining menus.
    """
    implements(ILinkData)

    def __init__(self, target, text, summary=None, icon=None, enabled=True,
                 site=None, menu=None, hidden=False):
        """Create a new link to 'target' with 'text' as the link text.

        'target' is a relative path, an absolute path, or an absolute url.

        'text' is the link text of this link.

        'summary' is the summary text of this link.

        The 'enabled' argument is boolean for whether this link is enabled.

        The 'icon' is the name of the icon to use, or None if there is no
        icon. This is currently unused in the Actions menu, but will likely
        be used when menu links are embedded in the page (bug 5313).

        The 'site' is None for whatever the current site is, and 'main' or
        'blueprint' for a specific site.

        :param menu: The sub menu used by the page that the link represents.
        """

        self.target = target
        self.text = text
        self.summary = summary
        self.icon = icon
        if not isinstance(enabled, bool):
            raise AssertionError("enabled must be boolean, got %r" % enabled)
        self.enabled = enabled
        self.site = site
        self.menu = menu
        self.hidden = hidden

Link = LinkData


class MenuLink:
    """Adapter from ILinkData to ILink."""
    implements(ILink)
    delegates(ILinkData, context='_linkdata')

    # These attributes are set by the menus infrastructure.
    name = None
    url = None
    linked = True

    # This attribute is used to override self.enabled when it is
    # set, without writing to the object being adapted.
    _enabled_override = None

    def __init__(self, linkdata):
        # Take a copy of the linkdata attributes.
        self._linkdata = linkdata

    def set_enabled(self, value):
        self._enabled_override = value

    def get_enabled(self):
        if self._enabled_override is None:
            return self._linkdata.enabled
        return self._enabled_override

    enabled = property(get_enabled, set_enabled)

    @property
    def escapedtext(self):
        # This is often an IStructuredString, which html_escape knows
        # to not double-escape.
        return html_escape(self._linkdata.text)

    @property
    def icon_url(self):
        """The full URL of this link's associated icon, if it has one."""
        if not self.icon:
            return
        else:
            return '/@@/%s' % self.icon

    def render(self):
        """See `ILink`."""
        return getMultiAdapter(
            (self, get_current_browser_request()), name="+inline")()

    @property
    def path(self):
        """See `ILink`."""
        return self.url.path


class FacetLink(MenuLink):
    """Adapter from ILinkData to IFacetLink."""
    implements(IFacetLink)

    # This attribute is set by the menus infrastructure.
    selected = False


# Marker object that means 'all links are to be enabled'.
ALL_LINKS = object()

MENU_ANNOTATION_KEY = 'lp.services.webapp.menu.links'


class MenuBase(UserAttributeCache):
    """Base class for facets and menus."""

    implements(IMenuBase)

    links = None
    extra_attributes = None
    enable_only = ALL_LINKS
    _baseclassname = 'MenuBase'
    _initialized = False
    _forbiddenlinknames = set(
        ['user', 'initialize', 'links', 'enable_only', 'iterlinks',
         'initLink', 'updateLink', 'extra_attributes'])

    def __init__(self, context):
        # The attribute self.context is defined in IMenuBase.
        self.context = context
        self.request = None

    def initialize(self):
        """Override this in subclasses to do initialization."""
        pass

    def _check_links(self):
        assert self.links is not None, (
            'Subclasses of %s must provide self.links' % self._baseclassname)
        assert isinstance(self.links, (tuple, list)), (
            "self.links must be a tuple or list.")

    def _buildLink(self, name):
        method = getattr(self, name, None)
        # Since Zope traversals hides the root cause of an AttributeError,
        # an AssertionError is raised explaining what went wrong.
        if method is None:
            raise AssertionError(
                '%r does not define %r method.' % (self, name))
        linkdata = method()
        # The link need only provide ILinkData.  We need an ILink so that
        # we can set attributes on it like 'name' and 'url' and 'linked'.
        return ILink(linkdata)

    def _get_link(self, name):
        request = get_current_browser_request()
        if request is not None:
            # We must not use a weak ref here because if we do so and
            # templates do stuff like "context/menu:bugs/foo", then there
            # would be no reference to the Link object, which would allow it
            # to be garbage collected during the course of the request.
            cache = request.annotations.setdefault(MENU_ANNOTATION_KEY, {})
            key = (self.__class__, self.context, name)
            link = cache.get(key)
            if link is None:
                link = self._buildLink(name)
                cache[key] = link
            return link
        return self._buildLink(name)

    def _rootUrlForSite(self, site):
        """Return the root URL for the given site."""
        try:
            return URI(allvhosts.configs[site].rooturl)
        except KeyError:
            raise AssertionError('unknown site', site)

    def _init_link_data(self):
        if self._initialized:
            return
        self._initialized = True
        self.initialize()
        self._check_links()
        links_set = set(self.links)
        assert not links_set.intersection(self._forbiddenlinknames), (
            "The following names may not be links: %s" %
            ', '.join(self._forbiddenlinknames))

        if isinstance(self.context, LaunchpadView):
            # It's a navigation menu for a view instead of a db object. Views
            # don't have a canonical URL, they use the db object one used as
            # the context for that view.
            context = self.context.context
        else:
            context = self.context

        self._contexturlobj = URI(canonical_url(context))

        if self.enable_only is ALL_LINKS:
            self._enable_only_set = links_set
        else:
            self._enable_only_set = set(self.enable_only)

        unknown_links = self._enable_only_set - links_set
        if len(unknown_links) > 0:
            # There are links named in enable_only that do not exist in
            # self.links.
            raise AssertionError(
                "Links in 'enable_only' not found in 'links': %s" %
                ', '.join(sorted(unknown_links)))

    def initLink(self, linkname, request_url=None):
        self._init_link_data()
        link = self._get_link(linkname)
        link.name = linkname

        # Set the .enabled attribute of the link to False if it is not
        # in enable_only.
        if linkname not in self._enable_only_set:
            link.enabled = False

        # Set the .url attribute of the link, using the menu's context.
        if link.site is None:
            rootsite = self._contexturlobj.resolve('/')
        else:
            rootsite = self._rootUrlForSite(link.site)
        # Is the target a full URI already?
        try:
            link.url = URI(link.target)
        except InvalidURIError:
            if link.target.startswith('/'):
                link.url = rootsite.resolve(link.target)
            else:
                link.url = rootsite.resolve(self._contexturlobj.path).append(
                    link.target)

        # Make the link unlinked if it is a link to the current page.
        if request_url is not None:
            if request_url.ensureSlash() == link.url.ensureSlash():
                link.linked = False

        idx = self.links.index(linkname)
        link.sort_key = idx
        return link

    def updateLink(self, link, request_url, **kwargs):
        """Called each time a link is rendered.

        Override to update the link state as required for the given request.
        """
        pass

    def iterlinks(self, request_url=None, **kwargs):
        """See IMenu."""
        self._check_links()
        for linkname in self.links:
            link = self.initLink(linkname, request_url)
            self.updateLink(link, request_url, **kwargs)
            yield link


class FacetMenu(MenuBase):
    """Base class for facet menus."""

    implements(IFacetMenu)

    _baseclassname = 'FacetMenu'

    # See IFacetMenu.
    defaultlink = None

    def _filterLink(self, name, link):
        """Hook to allow subclasses to alter links based on the name used."""
        return link

    def _get_link(self, name):
        return IFacetLink(
            self._filterLink(name, MenuBase._get_link(self, name)))

    def initLink(self, linkname, request_url=None):
        link = super(FacetMenu, self).initLink(linkname, request_url)
        link.url = link.url.ensureNoSlash()
        return link

    def updateLink(self, link, request_url=None, selectedfacetname=None):
        super(FacetMenu, self).updateLink(link, request_url)
        if selectedfacetname is None:
            selectedfacetname = self.defaultlink
        if (selectedfacetname is not None and
            selectedfacetname == link.name):
            link.selected = True


class ApplicationMenu(MenuBase):
    """Base class for application menus."""

    implements(IApplicationMenu)

    _baseclassname = 'ApplicationMenu'


class ContextMenu(MenuBase):
    """Base class for context menus."""

    implements(IContextMenu)

    _baseclassname = 'ContextMenu'


class NavigationMenu(MenuBase):
    """Base class for navigation menus."""

    implements(INavigationMenu)

    _baseclassname = 'NavigationMenu'

    title = None
    disabled = False

    def initLink(self, linkname, request_url):
        link = super(NavigationMenu, self).initLink(linkname, request_url)
        link.url = link.url.ensureNoSlash()
        return link

    def updateLink(self, link, request_url=None, view=None):
        super(NavigationMenu, self).updateLink(link, request_url)
        # The link should be unlinked if it is the current URL, or if
        # the menu for the current view is the link's menu.
        if view is None:
            view = get_current_view(self.request)
        link.linked = not (self._is_current_url(request_url, link.url)
                           or self._is_menulink_for_view(link, view))

    def iterlinks(self, request_url=None):
        """See `INavigationMenu`.

        Menus may be associated with content objects and their views. The
        state of a menu's links depends upon the request_url (or the URL of
        the request) and whether the current view's menu is the link's menu.
        """
        request = get_current_browser_request()
        view = get_current_view(request)
        if request_url is None:
            request_url = URI(request.getURL())

        for link in super(NavigationMenu, self).iterlinks(
            request_url=request_url, view=view):
            yield link

    def _is_current_url(self, request_url, link_url):
        """Determines if <link_url> is the current URL.

        There are two cases to consider:
        1) If the link target doesn't have query parameters, the request URL
        must be the same link (ignoring query parameters).
        2) If the link target has query parameters, the request url must be
        a prefix of it to be the current url.
        """
        if link_url.query is not None:
            return str(request_url).startswith(str(link_url))
        else:
            request_url_without_query = (
                request_url.replace(query=None).ensureNoSlash())
            return link_url == request_url_without_query

    def _is_menulink_for_view(self, link, view):
        """Return True if the menu-link is for the current view.

        :param link: An `ILink` in the menu. It has a menu attribute that may
            have an `INavigationMenu` assigned.
        :view: The view being tested.

        A link is considered to be selected when the view provides link's menu
        interface.
        """
        return (link.menu is not None and link.menu.providedBy(view))


class enabled_with_permission:
    """Function decorator that disables the output link unless the current
    user has the given permission on the context.

    This class is instantiated by programmers who want to apply this
    decorator.

    Use it like:

        @enabled_with_permission('launchpad.Admin')
        def somemenuitem(self):
            return Link('+target', 'link text')

    """

    def __init__(self, permission):
        """Make a new enabled_with_permission function decorator.

        `permission` is the string permission name, like 'launchpad.Admin'.
        """
        self.permission = permission

    def __call__(self, func):
        """Called by the decorator machinery to return a decorated function.

        Returns a new function that calls the original function, gets the
        link that it returns, and depending on the permissions granted to
        the logged-in user, disables the link, before returning it to the
        called.
        """
        permission = self.permission

        # This is imported here to forestall an import-time config read that
        # wreaks havoc.
        from lp.services.webapp.authorization import check_permission

        def enable_if_allowed(self):
            link = func(self)
            if not check_permission(permission, self.context):
                link.enabled = False
            return link
        return enable_if_allowed
