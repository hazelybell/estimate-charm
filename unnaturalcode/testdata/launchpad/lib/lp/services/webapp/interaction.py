# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Methods dealing with interactions.

Almost everything in Launchpad relies on a security policy, in particular
retrieving utilities and accessing attributes.

Zope obtains the security policy by looking at the 'interaction', which is a
thread-local variable. If there is no interaction, one is likely to encounter
an error like:

  AttributeError("'thread._local' object has no attribute 'interaction'")

In Launchpad, we frequently refer to the state of having no interaction as
being "logged out".

Because one needs an interaction to do practically anything, and because
Launchpad allows anonymous access, it is possible to create an interaction
(informally, "log in") for a mythical anonymous user.

The object representing the logged-in user is called the "principal", and the
relationship between the principal and the interaction is called the
"participation".

In Launchpad and in standard usage, the participation is the request and the
principal is the requesting user. Although Zope has support for more than one
of these, we only ever allow one.

There are test helpers in `lp.testing._login`.

See also lib/canonical/launchpad/doc/webapp-authorization.txt.
"""

__metaclass__ = type

from zope.authentication.interfaces import IUnauthenticatedPrincipal
from zope.component import getUtility
from zope.interface import implements
from zope.publisher.interfaces import IPublicationRequest
from zope.security.interfaces import IParticipation
from zope.security.management import (
    endInteraction,
    newInteraction,
    queryInteraction,
    )

from lp.services.webapp.interfaces import (
    IInteractionExtras,
    IOpenLaunchBag,
    IPlacelessAuthUtility,
    )


__all__ = [
    'ANONYMOUS',
    'get_current_principal',
    'get_interaction_extras',
    'setupInteraction',
    'setupInteractionByEmail',
    'setupInteractionForPerson',
    'InteractionExtras',
    ]


ANONYMOUS = 'launchpad.anonymous'


def get_current_principal():
    """Get the principal from the current interaction.

    :return: The current principal if there is an interaction, None otherwise.
    """
    interaction = queryInteraction()
    if interaction is None:
        return None
    principals = [
        participation.principal
        for participation in interaction.participations
        if participation.principal is not None]
    if not principals:
        return None
    elif len(principals) > 1:
        raise ValueError('Too many principals')
    else:
        return principals[0]


def setupInteraction(principal, login=None, participation=None):
    """Sets up a new interaction with the given principal.

    The login gets added to the launch bag.

    You can optionally pass in a participation to be used.  If no
    participation is given, a Participation is used.
    """
    # If principal is None, this method acts just like endInteraction.
    if principal is None:
        endInteraction()
        return

    if principal == ANONYMOUS:
        authutil = getUtility(IPlacelessAuthUtility)
        principal = authutil.unauthenticatedPrincipal()

    if participation is None:
        participation = Participation()

    # First end any running interaction, and start a new one.
    endInteraction()
    newInteraction(participation)

    launchbag = getUtility(IOpenLaunchBag)
    if IUnauthenticatedPrincipal.providedBy(principal):
        launchbag.setLogin(None)
    else:
        launchbag.setLogin(login)

    if IPublicationRequest.providedBy(participation):
        # principal is a read-only attribute on requests.
        participation.setPrincipal(principal)
    else:
        # Try setting the attribute directly.
        participation.principal = principal


def setupInteractionByEmail(email, participation=None):
    """Setup an interaction using an email.

    If the ANONYMOUS constant is supplied as the email,
    an interaction for the anonymous user will be used.

    You can optionally pass in a participation to be used.  If no
    participation is given, an empty participation is used.

    If the participation provides IPublicationRequest, it must implement
    setPrincipal(), otherwise it must allow setting its principal attribute.
    """
    authutil = getUtility(IPlacelessAuthUtility)

    if email != ANONYMOUS:
        # Create an anonymous interaction first because this calls
        # IPersonSet.getByEmail() and since this is security wrapped, it needs
        # an interaction available.
        setupInteraction(authutil.unauthenticatedPrincipal())
        principal = authutil.getPrincipalByLogin(email)
        assert principal is not None, "Invalid login"
        if principal.person is not None and principal.person.is_team:
            raise AssertionError("Please do not try to login as a team")
    else:
        principal = authutil.unauthenticatedPrincipal()

    if participation is None:
        participation = Participation()

    setupInteraction(principal, login=email, participation=participation)


def setupInteractionForPerson(person, participation=None):
    """Setup a participation for a person."""
    from zope.security.proxy import removeSecurityProxy
    if person is None:
        return setupInteraction(ANONYMOUS, participation)
    else:
        # Bypass zope's security because IEmailAddress.email is not public.
        naked_person = removeSecurityProxy(person)
        naked_email = removeSecurityProxy(naked_person.preferredemail)
        return setupInteractionByEmail(naked_email.email, participation)


class Participation:
    """A very simple participation."""
    implements(IParticipation)

    interaction = None
    principal = None


class InteractionExtras:
    """Extra data attached to all interactions.  See `IInteractionExtras`."""

    implements(IInteractionExtras)
    permit_timeout_from_features = False


def get_interaction_extras():
    """Return the active provider of `IInteractionExtras`.

    This is looked up from the interaction.  If there is no interaction then
    return None.
    """
    interaction = queryInteraction()
    if interaction is None:
        return None
    return interaction.extras
