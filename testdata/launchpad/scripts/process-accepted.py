#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Queue/Accepted processor

Given a distribution to run on, obtains all the queue items for the
distribution and then gets on and deals with any accepted items, preparing
them for publishing as appropriate.
"""

import _pythonpath

from lp.soyuz.scripts.processaccepted import ProcessAccepted


if __name__ == '__main__':
    script = ProcessAccepted(
        "process-accepted", dbuser='process_accepted')
    script.lock_and_run()
