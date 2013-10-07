# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for testing menus."""

__metaclass__ = type
__all__ = [
    'summarise_tal_links',
    'make_fake_request',
    ]

from lazr.restful.utils import safe_hasattr
from zope.security.management import (
    endInteraction,
    newInteraction,
    )
from zope.security.proxy import isinstance as zope_isinstance

from lp.services.webapp import urlsplit
from lp.services.webapp.interfaces import ILink
from lp.services.webapp.publisher import canonical_url
from lp.services.webapp.servers import LaunchpadTestRequest


def check_menu_links(menu):
    context = menu.context
    for link in menu.iterlinks():
        if link.target.startswith(('/', 'http://')):
            # The context is not the context of this target.
            continue
        if '?' in link.target:
            view_name, _args = link.target.split('?')
        else:
            view_name = link.target
        if view_name == '':
            view_name = None
        try:
            canonical_url(context, view_name=view_name, rootsite=link.site)
        except Exception:
            try:
                url = canonical_url(context)
            except Exception:
                url = repr(context)
            return 'Bad link %s: %s' % (link.name, url)
    return True


def summarise_tal_links(links):
    """List the links and their attributes in the dict or list.

    :param links: A dictionary or list of menu links returned by
        `lp.app.browser.tales.MenuAPI`.
    """
    is_dict = zope_isinstance(links, dict)
    if is_dict:
        keys = sorted(links)
    else:
        keys = links
    for key in keys:
        if is_dict:
            link = links[key]
        else:
            link = key
        if ILink.providedBy(link):
            print 'link %s' % link.name
            attributes = ('url', 'enabled', 'menu', 'selected', 'linked')
            for attrname in attributes:
                if not safe_hasattr(link, attrname):
                    continue
                print '    %s:' % attrname, getattr(link, attrname)
        else:
            print 'attribute %s: %s' % (key, link)


def make_fake_request(url, traversed_objects=None):
    """Return a fake request object for menu testing.

    :param traversed_objects: A list of objects that becomes the request's
        traversed_objects attribute.
    """
    url_parts = urlsplit(url)
    server_url = '://'.join(url_parts[0:2])
    path_info = url_parts[2]
    request = LaunchpadTestRequest(
        SERVER_URL=server_url,
        PATH_INFO=path_info)
    request._traversed_names = path_info.split('/')[1:]
    if traversed_objects is not None:
        request.traversed_objects = traversed_objects[:]
    # After making the request, setup a new interaction.
    endInteraction()
    newInteraction(request)
    return request
