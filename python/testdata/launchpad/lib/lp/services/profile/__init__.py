# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Profiling for Python and Zope applications.
"""

__all__ = ['profiling',
           'start',
           'stop',
          ]

# Re-export for convenience.
from lp.services.profile.profile import (
    profiling,
    start,
    stop,
    )

# Quiet the linter.
(profiling, start, stop)
