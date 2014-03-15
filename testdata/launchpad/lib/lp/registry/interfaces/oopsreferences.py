# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces for querying OOPS references."""

__metaclass__ = type

__all__ = [
    'IHasOOPSReferences',
    ]


from lazr.restful.declarations import (
    export_read_operation,
    operation_for_version,
    operation_parameters,
    )
from zope.interface import Interface
from zope.schema import Datetime

from lp import _


class IHasOOPSReferences(Interface):
    """Has references to OOPSes that can be queried."""

    @operation_parameters(
        start_date=Datetime(title=_("Modified after date")),
        end_date=Datetime(title=_("Modified before date")),
        )
    @export_read_operation()
    @operation_for_version('devel')
    def findReferencedOOPS(start_date, end_date):
        """Find OOPS reports between start_date and end_date.

        :param start_date: Do not look in objects whose last modification time
            is before this date.
        :param end_date: Do not look in objects whose last modification time
            is after this date.
        :return: A set of OOPS id's - strings of the form 'OOPS-\w+'.
        """
