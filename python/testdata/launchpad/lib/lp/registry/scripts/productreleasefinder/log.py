# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Logging.

This module contains a utility function for creating trees of logging
instances for objects.
"""

__metaclass__ = type


import logging


def get_logger(name, parent=None):
    """Create a logging instance underneath the given parent."""
    if parent is None or parent == parent.root:
        l = logging.getLogger(name)
    else:
        l = logging.getLogger("%s.%s" % (parent.name, name))

    return l
