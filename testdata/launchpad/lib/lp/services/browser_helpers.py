# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helpers for examining the browser user_agent header."""

__metaclass__ = type
__all__ = [
    'get_user_agent_distroseries',
    'get_plural_text',
    ]

import re


def get_user_agent_distroseries(user_agent_string):
    """Return the `DistroSeries` version number from the user-agent."""

    if user_agent_string is None:
        return None

    # We're matching on the Ubuntu/10.09 section of the user-agent string.
    pattern = 'Ubuntu/(?P<version>\d*\.\d*)'
    match = re.search(pattern, user_agent_string)

    if match is not None:
        # Great, the browser is telling us the platform is Ubuntu.
        # Now grab the Ubuntu series/version number:
        return match.groupdict()['version']
    else:
        return None


def get_plural_text(count, singular, plural):
    """Return 'singular' if 'count' is 1, 'plural' otherwise."""
    if count == 1:
        return singular
    else:
        return plural
