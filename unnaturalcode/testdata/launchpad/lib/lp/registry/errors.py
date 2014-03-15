# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'DistroSeriesDifferenceError',
    'NotADerivedSeriesError',
    'CannotChangeInformationType',
    'CannotDeleteCommercialSubscription',
    'CannotTransitionToCountryMirror',
    'CommercialSubscribersOnly',
    'CannotPackageProprietaryProduct',
    'CountryMirrorAlreadySet',
    'DeleteSubscriptionError',
    'InvalidFilename',
    'InvalidName',
    'JoinNotAllowed',
    'MirrorNotOfficial',
    'MirrorHasNoHTTPURL',
    'MirrorNotProbed',
    'NameAlreadyTaken',
    'NoSuchDistroSeries',
    'NoSuchSourcePackageName',
    'InclusiveTeamLinkageError',
    'PPACreationError',
    'PrivatePersonLinkageError',
    'ProprietaryProduct',
    'TeamMembershipTransitionError',
    'TeamMembershipPolicyError',
    'UserCannotChangeMembershipSilently',
    'UserCannotSubscribePerson',
    'VoucherAlreadyRedeemed',
    ]

import httplib

from lazr.restful.declarations import error_status
from zope.schema.interfaces import ConstraintNotSatisfied
from zope.security.interfaces import Unauthorized

from lp.app.errors import NameLookupFailed


@error_status(httplib.FORBIDDEN)
class PrivatePersonLinkageError(ValueError):
    """An attempt was made to link a private person/team to something."""


@error_status(httplib.FORBIDDEN)
class InclusiveTeamLinkageError(ValueError):
    """An attempt was made to link an open team to something."""


@error_status(httplib.CONFLICT)
class NameAlreadyTaken(Exception):
    """The name given for a person is already in use by other person."""


class InvalidName(Exception):
    """The name given for a person is not valid."""


@error_status(httplib.BAD_REQUEST)
class InvalidFilename(Exception):
    """An invalid filename was used as an attachment filename."""


class NoSuchDistroSeries(NameLookupFailed):
    """Raised when we try to find a DistroSeries that doesn't exist."""
    _message_prefix = "No such distribution series"


@error_status(httplib.UNAUTHORIZED)
class UserCannotChangeMembershipSilently(Unauthorized):
    """User not permitted to change membership status silently.

    Raised when a user tries to change someone's membership silently, and is
    not a Launchpad Administrator.
    """


@error_status(httplib.FORBIDDEN)
class CommercialSubscribersOnly(Unauthorized):
    """Feature is only available to current commercial subscribers.

    Raised when a user tries to invoke an operation that is only available to
    current commercial subscribers and they don't have an active subscription.
    """


class ProprietaryProduct(Exception):
    """Cannot make the change because the project is proprietary."""


class NoSuchSourcePackageName(NameLookupFailed):
    """Raised when we can't find a particular sourcepackagename."""
    _message_prefix = "No such source package"


@error_status(httplib.BAD_REQUEST)
class CannotTransitionToCountryMirror(Exception):
    """Root exception for transitions to country mirrors."""


class CountryMirrorAlreadySet(CannotTransitionToCountryMirror):
    """Distribution mirror cannot be set as a country mirror.

    Raised when a user tries to change set a distribution mirror as a country
    mirror, however there is already one set for that country.
    """


class MirrorNotOfficial(CannotTransitionToCountryMirror):
    """Distribution mirror is not permitted to become a country mirror.

    Raised when a user tries to change set a distribution mirror as a country
    mirror, however the mirror in question is not official.
    """


class MirrorHasNoHTTPURL(CannotTransitionToCountryMirror):
    """Distribution mirror has no HTTP URL.

    Raised when a user tries to make an official mirror a country mirror,
    however the mirror has not HTTP URL set.
    """


class MirrorNotProbed(CannotTransitionToCountryMirror):
    """Distribution mirror has not been probed.

    Raised when a user tries to set an official mirror as a country mirror,
    however the mirror has not been probed yet.
    """


@error_status(httplib.BAD_REQUEST)
class DeleteSubscriptionError(Exception):
    """Delete Subscription Error.

    Raised when an error occurred trying to delete a
    structural subscription."""


@error_status(httplib.UNAUTHORIZED)
class UserCannotSubscribePerson(Exception):
    """User does not have permission to subscribe the person or team."""


@error_status(httplib.BAD_REQUEST)
class DistroSeriesDifferenceError(Exception):
    """Raised when package diffs cannot be created for a difference."""


class NotADerivedSeriesError(Exception):
    """A distro series difference must be created with a derived series.

    This is raised when a DistroSeriesDifference is created with a
    non-derived series - that is, a distroseries with a null Parent."""


@error_status(httplib.BAD_REQUEST)
class TeamMembershipTransitionError(ValueError):
    """Indicates something has gone wrong with the transtiion.

    Generally, this indicates a bad transition (e.g. approved to proposed)
    or an invalid transition (e.g. unicorn).
    """


@error_status(httplib.BAD_REQUEST)
class TeamMembershipPolicyError(ConstraintNotSatisfied):
    """The team cannot have the specified TeamMembershipPolicy.

    The error can be raised because a super team or member team prevents
    this team from setting a specific policy. The error can also be
    raised if the team has an active PPA.
    """

    _default_message = "Team Membership Policy Error"

    def __init__(self, message=None):
        if message is None:
            message = self._default_message
        self.message = message

    def doc(self):
        """See `Invalid`."""
        return self.message

    def __str__(self):
        return self.message


@error_status(httplib.BAD_REQUEST)
class JoinNotAllowed(Exception):
    """User is not allowed to join a given team."""


@error_status(httplib.BAD_REQUEST)
class PPACreationError(Exception):
    """Raised when there is an issue creating a new PPA."""


class CannotDeleteCommercialSubscription(Exception):
    """Raised when a commercial subscription cannot be deleted."""


@error_status(httplib.BAD_REQUEST)
class CannotChangeInformationType(Exception):
    """The information type cannot be changed."""


class CannotPackageProprietaryProduct(Exception):
    """Raised when a non-PUBLIC product's series is linked to a package."""


class VoucherAlreadyRedeemed(Exception):
    """Raised when a voucher is redeemed more than once."""
