# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The webapp package contains infrastructure that is common across Launchpad
that is to do with aspects such as security, menus, zcml, tales and so on.

This module also has an API for use by the application.
"""
__metaclass__ = type

__all__ = [
    'ApplicationMenu',
    'canonical_name',
    'canonical_url',
    'ContextMenu',
    'available_with_permission',
    'enabled_with_permission',
    'expand_numbers',
    'FacetMenu',
    'GetitemNavigation',
    'LaunchpadView',
    'LaunchpadXMLRPCView',
    'Link',
    'Navigation',
    'NavigationMenu',
    'nearest',
    'redirection',
    'sorted_dotted_numbers',
    'sorted_version_numbers',
    'StandardLaunchpadFacets',
    'stepthrough',
    'stepto',
    'structured',
    'urlappend',
    'urlparse',
    'urlsplit',
    'Utf8PreferredCharsets',
    ]

from lp.services.webapp.escaping import structured
from lp.services.webapp.menu import (
    ApplicationMenu,
    ContextMenu,
    enabled_with_permission,
    FacetMenu,
    Link,
    NavigationMenu,
    )
from lp.services.webapp.preferredcharsets import Utf8PreferredCharsets
from lp.services.webapp.publisher import (
    canonical_name,
    canonical_url,
    LaunchpadView,
    LaunchpadXMLRPCView,
    Navigation,
    nearest,
    redirection,
    stepthrough,
    stepto,
    )
from lp.services.webapp.sorting import (
    expand_numbers,
    sorted_dotted_numbers,
    sorted_version_numbers,
    )
from lp.services.webapp.url import (
    urlappend,
    urlparse,
    urlsplit,
    )


class GetitemNavigation(Navigation):
    """Base class for navigation where fall-back traversal uses context[name].
    """

    def traverse(self, name):
        return self.context[name]


class StandardLaunchpadFacets(FacetMenu):
    """The standard set of facets that most faceted content objects have."""

    # provide your own 'usedfor' in subclasses.
    #   usedfor = IWhatever

    links = ['overview', 'branches', 'bugs', 'specifications', 'translations',
             'answers']

    enable_only = ['overview', 'bugs', 'specifications', 'translations']

    defaultlink = 'overview'

    def _filterLink(self, name, link):
        if link.site is None:
            if name == 'specifications':
                link.site = 'blueprints'
            elif name == 'branches':
                link.site = 'code'
            elif name == 'translations':
                link.site = 'translations'
            elif name == 'answers':
                link.site = 'answers'
            elif name == 'bugs':
                link.site = 'bugs'
            else:
                link.site = 'mainsite'
        return link

    def overview(self):
        text = 'Overview'
        return Link('', text)

    def translations(self):
        text = 'Translations'
        return Link('', text)

    def bugs(self):
        text = 'Bugs'
        return Link('', text)

    def answers(self):
        # This facet is visible but unavailable by default.
        # See the enable_only list above.
        text = 'Answers'
        summary = 'Launchpad Answer Tracker'
        return Link('', text, summary)

    def specifications(self):
        text = 'Blueprints'
        summary = 'Blueprints and specifications'
        return Link('', text, summary)

    def branches(self):
        # this is disabled by default, because relatively few objects have
        # branch views
        text = 'Code'
        summary = 'View related code'
        return Link('', text, summary=summary)
