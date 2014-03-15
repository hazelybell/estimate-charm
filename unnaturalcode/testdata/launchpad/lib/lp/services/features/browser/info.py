# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View and edit feature rules."""

__metaclass__ = type
__all__ = [
    'FeatureInfoView',
    ]


from collections import namedtuple

from lp.services.features.flags import (
    flag_info,
    undocumented_flags,
    value_domain_info,
    )
from lp.services.features.scopes import (
    HANDLERS,
    undocumented_scopes,
    )
from lp.services.utils import docstring_dedent
from lp.services.webapp.publisher import LaunchpadView

# Named tuples to use when passing flag and scope data to the template.
Flag = namedtuple(
    'Flag', ('name', 'domain', 'description', 'default', 'title', 'link'))
ValueDomain = namedtuple('ValueDomain', ('name', 'description'))
Scope = namedtuple('Scope', ('regex', 'description'))


class FeatureInfoView(LaunchpadView):
    """Display feature flag documentation and other info."""

    page_title = label = 'Feature flag info'

    @property
    def flag_info(self):
        """A list of flags as named tuples, ready to be rendered."""
        return map(Flag._make, flag_info)

    @property
    def undocumented_flags(self):
        """Flag names referenced during process lifetime but not documented.
        """
        return ', '.join(undocumented_flags)

    @property
    def value_domain_info(self):
        """A list of flags as named tuples, ready to be rendered."""
        return map(ValueDomain._make, value_domain_info)

    @property
    def undocumented_scopes(self):
        """Scope names referenced during process lifetime but not documented.
        """
        return ', '.join(undocumented_scopes)

    @property
    def scope_info(self):
        """A list of scopes as named tuples, ready to be rendered."""
        return [
            Scope._make((handler.pattern, docstring_dedent(handler.__doc__)))
            for handler in HANDLERS]
