# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = ['IParsedApacheLog']

from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    TextLine,
    )

from lp import _


class IParsedApacheLog(Interface):
    """An apache log file parsed to extract download counts of files.

    This is used so that we don't parse log files more than once.
    """

    first_line = TextLine(
        title=_("The log file's first line"), required=True,
        readonly=True)
    bytes_read = Int(
        title=_('Number of bytes read'), required=True, readonly=False)
    date_last_parsed = Datetime(
        title=_('Date last parsed'), required=False, readonly=False)
