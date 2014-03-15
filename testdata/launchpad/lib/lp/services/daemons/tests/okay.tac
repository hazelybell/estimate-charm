# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
This TAC is used for the TacTestSetupTestCase.test_pidForNotRunningProcess
test case in test_tachandler.py.  It simply starts up correctly.
"""

__metaclass__ = type

from twisted.application import service

from lp.services.daemons import readyservice


application = service.Application('Okay')

# Service that announces when the daemon is ready
readyservice.ReadyService().setServiceParent(application)
