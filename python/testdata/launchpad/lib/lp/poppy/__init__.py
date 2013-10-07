# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# Make this directory into a Python package.

import os

from lp.services.config import config


def get_poppy_root():
    """Return the poppy root to use for this server.

    If the POPPY_ROOT environment variable is set, use that. If not, use
    config.poppy.fsroot.
    """
    poppy_root = os.environ.get('POPPY_ROOT', None)
    if poppy_root:
        return poppy_root
    return config.poppy.fsroot
