# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

# XXX matsubara 2010-07-16 bug=606303: NullHandler class is available on
# python 2.7 so when LP is running with it, this module can be removed.

import logging


class NullHandler(logging.Handler):
    def emit(self, record):
        pass
