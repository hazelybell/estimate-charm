# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Scripts that are used in developing Launchpad."""

import os


def get_launchpad_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
