# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Initializes the application after ZCML has been processed."""

from zope.component import (
    adapter,
    getSiteManager,
    )
from zope.interface import (
    implementer,
    Interface,
    )
from zope.processlifetime import IDatabaseOpened
from zope.publisher.interfaces import IRequest
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.publisher.interfaces.http import IHTTPRequest
from zope.traversing.interfaces import ITraversable


@implementer(Interface)
def adapter_mask(*args):
    return None


@adapter(IDatabaseOpened)
def handle_process_start(ev):
    """Post-process ZCML configuration.

    Normal configuration should happen in ZCML (or whatever our Zope
    configuration standard might become in the future).  The only kind
    of configuration that should happen here is automated fix-up
    configuration. Code below should call functions, each of which explains
    why it cannot be performed in ZCML.

    Also see the lp_sitecustomize module for initialization that is done when
    Python first starts.
    """
    fix_up_namespace_traversers()


def fix_up_namespace_traversers():
    """Block namespace traversers from being found as normal views.

    See bug 589010.

    This is done in a function rather than in ZCML because automation is
    appropriate: there has already been an explicit registration of the
    namespace, and having to also say "please don't assume it is a view"
    is a DRY violation that we can avoid.
    """
    sm = getSiteManager()
    info = 'see %s.fix_up_namespace_traversers' % (__name__,)
    namespace_factories = sm.adapters.lookupAll(
        (Interface, IBrowserRequest), ITraversable)
    for request_iface in (Interface, IRequest, IHTTPRequest, IBrowserRequest):
        for name, factory in namespace_factories:
            current = sm.adapters.lookup(
                (Interface, request_iface), Interface, name)
            if current is factory:
                sm.registerAdapter(
                    adapter_mask,
                    required=(Interface, request_iface), name=name, info=info)
