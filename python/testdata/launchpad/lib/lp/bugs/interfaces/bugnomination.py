# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces related to bug nomination."""

__metaclass__ = type

__all__ = [
    'BugNominationStatusError',
    'NominationError',
    'IBugNomination',
    'IBugNominationForm',
    'IBugNominationSet',
    'BugNominationStatus',
    'NominationSeriesObsoleteError']

import httplib

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.restful.declarations import (
    call_with,
    error_status,
    export_as_webservice_entry,
    export_read_operation,
    export_write_operation,
    exported,
    REQUEST_USER,
    )
from lazr.restful.fields import (
    Reference,
    ReferenceChoice,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.schema import (
    Choice,
    Datetime,
    Int,
    Set,
    )

from lp import _
from lp.app.validators.validation import can_be_nominated_for_series
from lp.bugs.interfaces.bug import IBug
from lp.bugs.interfaces.bugtarget import IBugTarget
from lp.bugs.interfaces.hasbug import IHasBug
from lp.registry.interfaces.distroseries import IDistroSeries
from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.role import IHasOwner
from lp.services.fields import PublicPersonChoice


@error_status(httplib.BAD_REQUEST)
class NominationError(Exception):
    """The bug cannot be nominated for this release."""


@error_status(httplib.BAD_REQUEST)
class NominationSeriesObsoleteError(Exception):
    """A bug cannot be nominated for an obsolete series."""


@error_status(httplib.BAD_REQUEST)
class BugNominationStatusError(Exception):
    """A error occurred while trying to set a bug nomination status."""


class BugNominationStatus(DBEnumeratedType):
    """Bug Nomination Status.

    The status of the decision to fix a bug in a specific release.
    """

    PROPOSED = DBItem(10, """
        Nominated

        This nomination hasn't yet been reviewed, or is still under
        review.
        """)

    APPROVED = DBItem(20, """
        Approved

        The release management team has approved fixing the bug for this
        release.
        """)

    DECLINED = DBItem(30, """
        Declined

        The release management team has declined fixing the bug for this
        release.
        """)


class IBugNomination(IHasBug, IHasOwner):
    """A nomination for a bug to be fixed in a specific series.

    A nomination can apply to an IDistroSeries or an IProductSeries.
    """
    export_as_webservice_entry(publish_web_link=False)

    # We want to customize the titles and descriptions of some of the
    # attributes of our parent interfaces, so we redefine those specific
    # attributes below.
    id = Int(title=_("Bug Nomination #"))
    bug = exported(Reference(schema=IBug, readonly=True))
    date_created = exported(Datetime(
        title=_("Date Submitted"),
        description=_("The date on which this nomination was submitted."),
        required=True, readonly=True))
    date_decided = exported(Datetime(
        title=_("Date Decided"),
        description=_(
            "The date on which this nomination was approved or declined."),
        required=False, readonly=True))
    distroseries = exported(ReferenceChoice(
        title=_("Series"), required=False, readonly=True,
        vocabulary="DistroSeries", schema=IDistroSeries))
    productseries = exported(ReferenceChoice(
        title=_("Series"), required=False, readonly=True,
        vocabulary="ProductSeries", schema=IProductSeries))
    owner = exported(PublicPersonChoice(
        title=_('Submitter'), required=True, readonly=True,
        vocabulary='ValidPersonOrTeam'))
    ownerID = Attribute('The db id of the owner.')
    decider = exported(PublicPersonChoice(
        title=_('Decided By'), required=False, readonly=True,
        vocabulary='ValidPersonOrTeam'))
    target = exported(Reference(
        schema=IBugTarget,
        title=_("The IProductSeries or IDistroSeries of this nomination.")))
    status = exported(Choice(
        title=_("Status"), vocabulary=BugNominationStatus,
        default=BugNominationStatus.PROPOSED, readonly=True))

    @call_with(approver=REQUEST_USER)
    @export_write_operation()
    def approve(approver):
        """Approve this bug for fixing in a series.

        :approver: The IPerson that approves this nomination and that
                   will own the created bugtasks.

        The status is set to APPROVED and the appropriate IBugTask(s)
        are created for the nomination target.

        A nomination in any state can be approved. If the nomination is
        /already/ approved, this method is a noop.
        """

    @call_with(decliner=REQUEST_USER)
    @export_write_operation()
    def decline(decliner):
        """Decline this bug for fixing in a series.

        :decliner: The IPerson that declines this nomination.

        The status is set to DECLINED.

        If called on a nomination that is in APPROVED state, a
        BugNominationStatusError is raised. If the nomination was
        already DECLINED, this method is a noop.
        """

    # Helper methods for making status checking more readable.
    def isProposed():
        """Is this nomination in Proposed state?"""

    def isDeclined():
        """Is this nomination in Declined state?"""

    def isApproved():
        """Is this nomination in Approved state?"""

    @call_with(person=REQUEST_USER)
    @export_read_operation()
    def canApprove(person):
        """Is this person allowed to approve the nomination?"""


class IBugNominationSet(Interface):
    """The set of IBugNominations."""

    def get(id):
        """Get a nomination by its ID.

        Returns an IBugNomination. Raises a NotFoundError is the
        nomination was not found.
        """


class IBugNominationForm(Interface):
    """The browser form for nominating bugs for series."""

    nominatable_series = Set(
        title=_("Series that can be nominated"), required=True,
        value_type=Choice(vocabulary="BugNominatableSeries"),
        constraint=can_be_nominated_for_series)
