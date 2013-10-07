# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'admin_logged_in',
    'anonymous_logged_in',
    'celebrity_logged_in',
    'login',
    'login_as',
    'login_celebrity',
    'login_person',
    'login_team',
    'logout',
    'person_logged_in',
    'run_with_login',
    'with_anonymous_login',
    'with_celebrity_logged_in',
    'with_person_logged_in',
    ]

from contextlib import contextmanager

from zope.component import getUtility
from zope.security.management import (
    endInteraction,
    queryInteraction,
    thread_local as zope_security_thread_local,
    )

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.utils import decorate_with
from lp.services.webapp.interaction import (
    ANONYMOUS,
    setupInteractionByEmail,
    setupInteractionForPerson,
    )
from lp.services.webapp.interfaces import ILaunchBag
from lp.services.webapp.servers import LaunchpadTestRequest
from lp.services.webapp.vhosts import allvhosts
from lp.testing.sampledata import ADMIN_EMAIL


def _test_login_impl(participation):
    # Common implementation of the test login wrappers.
    # It creates a default participation if None was specified.

    if participation is None:
        # we use the main site as the host name.  This is a guess, to make
        # canonical_url produce a real-looking host name rather than
        # 127.0.0.1.
        participation = LaunchpadTestRequest(
            environ={'HTTP_HOST': allvhosts.configs['mainsite'].hostname,
                     'SERVER_URL': allvhosts.configs['mainsite'].rooturl})
    return participation


def login(email, participation=None):
    """Simulates a login, using the specified email.

    If the lp.testing.ANONYMOUS constant is supplied
    as the email, you'll be logged in as the anonymous user.

    You can optionally pass in a participation to be used.  If no
    participation is given, a LaunchpadTestRequest is used.

    If the participation provides IPublicationRequest, it must implement
    setPrincipal(), otherwise it must allow setting its principal attribute.
    """

    if not isinstance(email, basestring):
        raise ValueError("Expected email parameter to be a string.")
    participation = _test_login_impl(participation)
    setupInteractionByEmail(email, participation)


def login_person(person, participation=None):
    """Login the person with their preferred email."""
    if person is not None:
        # The login will fail even without this check, but this gives us a
        # nice error message, which can save time when debugging.
        if getattr(person, 'is_team', None):
            raise ValueError("Got team, expected person: %r" % (person,))
    participation = _test_login_impl(participation)
    setupInteractionForPerson(person, participation)
    return person


def login_team(team, participation=None):
    """Login as a member of 'team'."""
    # Prevent import loop.
    from lp.testing.factory import LaunchpadObjectFactory
    if not team.is_team:
        raise ValueError("Got person, expected team: %r" % (team,))
    login(ADMIN_EMAIL)
    person = LaunchpadObjectFactory().makePerson()
    team.addMember(person, person)
    login_person(person, participation=participation)
    return person


def login_as(person_or_team, participation=None):
    """Login as a person or a team.

    :param person_or_team: A person, a team, ANONYMOUS or None. None and
        ANONYMOUS are equivalent, and will log the person in as the anonymous
        user.
    """
    if person_or_team == ANONYMOUS:
        login_method = login
    elif person_or_team is None:
        login_method = login_person
    elif person_or_team.is_team:
        login_method = login_team
    else:
        login_method = login_person
    return login_method(person_or_team, participation=participation)


def login_celebrity(celebrity_name, participation=None):
    """Login as a celebrity."""
    login(ANONYMOUS)
    celebs = getUtility(ILaunchpadCelebrities)
    celeb = getattr(celebs, celebrity_name, None)
    if celeb is None:
        raise ValueError("No such celebrity: %r" % (celebrity_name,))
    return login_as(celeb, participation=participation)


def login_admin(ignored, participation=None):
    """Log in as an admin."""
    login(ANONYMOUS)
    admin = getUtility(ILaunchpadCelebrities).admin.teamowner
    return login_as(admin, participation=participation)


def logout():
    """Tear down after login(...), ending the current interaction.

    Note that this is done automatically in
    LaunchpadFunctionalTestCase's tearDown method so
    you generally won't need to call this.
    """
    # Ensure the launchbag developer flag is off when logging out.
    getUtility(ILaunchBag).setDeveloper(False)
    endInteraction()


def _with_login(login_method, identifier):
    """Make a context manager that runs with a particular log in."""
    interaction = queryInteraction()
    person = login_method(identifier)
    try:
        yield person
    finally:
        if interaction is None:
            logout()
        else:
            # This reaches under the covers of the zope.security.management
            # module's interface in order to provide true nestable
            # interactions.  This means that real requests can be maintained
            # across these calls, such as is desired for yuixhr fixtures.
            zope_security_thread_local.interaction = interaction


@contextmanager
def person_logged_in(person):
    """Make a context manager for running logged in as 'person'.

    :param person: A person, an account, a team or ANONYMOUS. If a team,
        will log in as an arbitrary member of that team.
    """
    return _with_login(login_as, person)


@contextmanager
def anonymous_logged_in():
    """Make a context manager for running with the anonymous log in."""
    return _with_login(login_as, ANONYMOUS)


@contextmanager
def celebrity_logged_in(celebrity_name):
    """Make a context manager for running logged in as a celebrity."""
    return _with_login(login_celebrity, celebrity_name)


@contextmanager
def admin_logged_in():
    # Use teamowner to avoid expensive and noisy team member additions.
    return _with_login(login_admin, None)


with_anonymous_login = decorate_with(person_logged_in, None)


def with_person_logged_in(person):
    return decorate_with(person_logged_in, person)


def with_celebrity_logged_in(celebrity_name):
    """Decorate a function so that it's run with a celebrity logged in."""
    return decorate_with(celebrity_logged_in, celebrity_name)


def run_with_login(person, function, *args, **kwargs):
    """Run 'function' with 'person' logged in."""
    with person_logged_in(person):
        return function(*args, **kwargs)
