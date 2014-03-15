# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
LaunchBag

The collection of stuff we have traversed.
"""
__metaclass__ = type

import threading

import pytz
from zope.component import getUtility
from zope.interface import implements

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.blueprints.interfaces.specification import ISpecification
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugtask import IBugTask
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.person import IPerson
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.projectgroup import IProjectGroup
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.services.database.sqlbase import block_implicit_flushes
from lp.services.identity.interfaces.account import IAccount
from lp.services.webapp.interaction import get_current_principal
from lp.services.webapp.interfaces import (
    ILaunchBag,
    ILoggedInEvent,
    IOpenLaunchBag,
    )
from lp.soyuz.interfaces.distroarchseries import IDistroArchSeries


_utc_tz = pytz.timezone('UTC')


class LaunchBag:

    implements(IOpenLaunchBag)

    # Map Interface to attribute name.
    _registry = {
        IPerson: 'person',
        IProjectGroup: 'project',
        IProduct: 'product',
        IDistribution: 'distribution',
        IDistroSeries: 'distroseries',
        IDistroArchSeries: 'distroarchseries',
        ISourcePackage: 'sourcepackage',
        ISpecification: 'specification',
        IBug: 'bug',
        IBugTask: 'bugtask',
        }

    _store = threading.local()

    def setLogin(self, login):
        '''See IOpenLaunchBag.'''
        self._store.login = login

    @property
    def login(self):
        return getattr(self._store, 'login', None)

    def setDeveloper(self, is_developer):
        '''See IOpenLaunchBag.'''
        self._store.developer = is_developer

    @property
    def developer(self):
        return getattr(self._store, 'developer', False)

    @property
    @block_implicit_flushes
    def account(self):
        return IAccount(get_current_principal(), None)

    @property
    @block_implicit_flushes
    def user(self):
        return IPerson(get_current_principal(), None)

    def add(self, obj):
        store = self._store
        for interface, attribute in self._registry.items():
            if interface.providedBy(obj):
                setattr(store, attribute, obj)

    def clear(self):
        store = self._store
        for attribute in self._registry.values():
            setattr(store, attribute, None)
        store.login = None
        store.time_zone = None

    @property
    def person(self):
        return self._store.person

    @property
    def project(self):
        store = self._store
        if store.project is not None:
            return store.project
        elif store.product is not None:
            return store.product.project
        else:
            return None

    @property
    def product(self):
        return getattr(self._store, "product", None)

    @property
    def distribution(self):
        return getattr(self._store, "distribution", None)

    @property
    def distroseries(self):
        return self._store.distroseries

    @property
    def distroarchseries(self):
        return self._store.distroarchseries

    @property
    def sourcepackage(self):
        return self._store.sourcepackage

    @property
    def sourcepackagereleasepublishing(self):
        return self._store.sourcepackagereleasepublishing

    @property
    def specification(self):
        return self._store.specification

    @property
    def bug(self):
        if self._store.bug:
            return self._store.bug
        if self._store.bugtask:
            return self._store.bugtask.bug

    @property
    def bugtask(self):
        return getattr(self._store, "bugtask", None)

    @property
    def time_zone(self):
        if getattr(self._store, "time_zone", None) is None:
            if self.user and self.user.time_zone:
                self._store.time_zone = pytz.timezone(self.user.time_zone)
            else:
                # fall back to UTC
                self._store.time_zone = _utc_tz
        return self._store.time_zone


def set_login_in_launchbag_when_principal_identified(event):
    """This IPrincipalIdentifiedEvent subscriber sets 'login' in launchbag.
    """
    launchbag = getUtility(IOpenLaunchBag)
    # Basic auths principal identified event is also an ILoggedInEvent.
    # Cookie auth separates these two events.
    loggedinevent = ILoggedInEvent(event, None)
    if loggedinevent is None:
        # We must be using session auth.
        launchbag.setLogin(event.login)
    else:
        launchbag.setLogin(loggedinevent.login)


def set_developer_in_launchbag_before_traversal(event):
    """Subscriber for IBeforeTraverseEvent

    Sets the 'user is a launchpad developer flag' early, as we need
    it available if an exception occurs; If we leave it until needed,
    we may no longer have the functionality we need to look this up.
    """
    launchbag = getUtility(IOpenLaunchBag)
    user = launchbag.user
    if user is None:
        launchbag.setDeveloper(False)
    else:
        celebrities = getUtility(ILaunchpadCelebrities)
        is_developer = user.inTeam(celebrities.launchpad_developers)
        launchbag.setDeveloper(is_developer)


def reset_login_in_launchbag_on_logout(event):
    """Subscriber for ILoggedOutEvent that sets 'login' in launchbag to None.
    """
    launchbag = getUtility(IOpenLaunchBag)
    launchbag.setLogin(None)


def reset_developer_in_launchbag_on_logout(event):
    """Subscriber for ILoggedOutEvent that resets the developer flag."""
    launchbag = getUtility(IOpenLaunchBag)
    launchbag.setDeveloper(False)
