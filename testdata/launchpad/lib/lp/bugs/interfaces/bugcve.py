# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""BugCve linker interfaces."""

__metaclass__ = type

__all__ = ['IBugCve']

from zope.schema import Object

from lp import _
from lp.bugs.interfaces.buglink import IBugLink
from lp.bugs.interfaces.cve import ICve


class IBugCve(IBugLink):
    """A link between a bug and a CVE entry."""

    cve = Object(title=_('Cve Sequence'), required=True, readonly=True,
        description=_("Enter the CVE sequence number (XXXX-XXXX) that "
        "describes the same issue as this bug is addressing."),
        schema=ICve)

