# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import os


here = os.path.dirname(os.path.realpath(__file__))


def datadir(path):
    """Return fully-qualified path inside the test data directory."""
    if path.startswith("/"):
        raise ValueError("Path is not relative: %s" % path)
    return os.path.join(here, 'data', path)
