# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Run the doctests and pagetests.
"""

import logging
import os
import unittest

from lp.code.tests.test_doc import branchscannerSetUp
from lp.services.config import config
from lp.services.mail.tests.test_doc import ProcessMailLayer
from lp.soyuz.tests.test_doc import (
    lobotomize_stevea,
    uploaderSetUp,
    uploadQueueSetUp,
    )
from lp.testing import (
    login,
    logout,
    )
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import (
    DatabaseLayer,
    LaunchpadFunctionalLayer,
    LaunchpadZopelessLayer,
    )
from lp.testing.pages import PageTestSuite
from lp.testing.systemdocs import (
    LayeredDocFileSuite,
    setUp,
    tearDown,
    )


here = os.path.dirname(os.path.realpath(__file__))


def lobotomizeSteveASetUp(test):
    """Call lobotomize_stevea() and standard setUp"""
    lobotomize_stevea()
    setUp(test)


def checkwatchesSetUp(test):
    """Setup the check watches script tests."""
    setUp(test)
    switch_dbuser(config.checkwatches.dbuser)


def branchscannerBugsSetUp(test):
    """Setup the user for the branch scanner tests."""
    lobotomize_stevea()
    branchscannerSetUp(test)


def bugNotificationSendingSetUp(test):
    lobotomize_stevea()
    switch_dbuser(config.malone.bugnotification_dbuser)
    setUp(test)


def bugNotificationSendingTearDown(test):
    tearDown(test)


def cveSetUp(test):
    lobotomize_stevea()
    switch_dbuser(config.cveupdater.dbuser)
    setUp(test)


def uploaderBugsSetUp(test):
    """Set up a test suite using the 'uploader' db user.

    Some aspects of the bug tracker are being used by the Soyuz uploader.
    In order to test that these functions work as expected from the uploader,
    we run them using the same db user used by the uploader.
    """
    lobotomize_stevea()
    test_dbuser = config.uploader.dbuser
    switch_dbuser(test_dbuser)
    setUp(test)
    test.globs['test_dbuser'] = test_dbuser


def uploaderBugsTearDown(test):
    logout()


def uploadQueueTearDown(test):
    logout()


def noPrivSetUp(test):
    """Set up a test logged in as no-priv."""
    setUp(test)
    login('no-priv@canonical.com')


def bugtaskExpirationSetUp(test):
    """Setup globs for bug expiration."""
    setUp(test)
    login('test@canonical.com')


def updateRemoteProductSetup(test):
    """Setup to use the 'updateremoteproduct' db user."""
    setUp(test)
    switch_dbuser(config.updateremoteproduct.dbuser)


def updateRemoteProductTeardown(test):
    # Mark the DB as dirty, since we run a script in a sub process.
    DatabaseLayer.force_dirty_database()
    tearDown(test)


def bugSetStatusSetUp(test):
    setUp(test)
    test.globs['test_dbuser'] = config.processmail.dbuser


def bugmessageSetUp(test):
    setUp(test)
    login('no-priv@canonical.com')


special = {
    'cve-update.txt': LayeredDocFileSuite(
        '../doc/cve-update.txt',
        setUp=cveSetUp, tearDown=tearDown, layer=LaunchpadZopelessLayer
        ),
    'bug-heat.txt': LayeredDocFileSuite(
        '../doc/bug-heat.txt',
        setUp=setUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugnotificationrecipients.txt-uploader': LayeredDocFileSuite(
        '../doc/bugnotificationrecipients.txt',
        id_extensions=['bugnotificationrecipients.txt-uploader'],
        setUp=uploaderBugsSetUp,
        tearDown=uploaderBugsTearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugnotificationrecipients.txt-queued': LayeredDocFileSuite(
        '../doc/bugnotificationrecipients.txt',
        id_extensions=['bugnotificationrecipients.txt-queued'],
        setUp=uploadQueueSetUp,
        tearDown=uploadQueueTearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugnotificationrecipients.txt-branchscanner': LayeredDocFileSuite(
        '../doc/bugnotificationrecipients.txt',
        id_extensions=['bugnotificationrecipients.txt-branchscanner'],
        setUp=branchscannerBugsSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugnotificationrecipients.txt': LayeredDocFileSuite(
        '../doc/bugnotificationrecipients.txt',
        id_extensions=['bugnotificationrecipients.txt'],
        setUp=lobotomizeSteveASetUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer
        ),
    'bugnotification-threading.txt': LayeredDocFileSuite(
        '../doc/bugnotification-threading.txt',
        setUp=lobotomizeSteveASetUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer
        ),
    'bugnotification-sending.txt': LayeredDocFileSuite(
        '../doc/bugnotification-sending.txt',
        layer=LaunchpadZopelessLayer, setUp=bugNotificationSendingSetUp,
        tearDown=bugNotificationSendingTearDown
        ),
    'bugmail-headers.txt': LayeredDocFileSuite(
        '../doc/bugmail-headers.txt',
        layer=LaunchpadZopelessLayer,
        setUp=bugNotificationSendingSetUp,
        tearDown=bugNotificationSendingTearDown),
    'bug-export.txt': LayeredDocFileSuite(
        '../doc/bug-export.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bug-set-status.txt': LayeredDocFileSuite(
        '../doc/bug-set-status.txt',
        id_extensions=['bug-set-status.txt'],
        setUp=uploadQueueSetUp,
        tearDown=uploadQueueTearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bug-set-status.txt-uploader': LayeredDocFileSuite(
        '../doc/bug-set-status.txt',
        id_extensions=['bug-set-status.txt-uploader'],
        setUp=uploaderBugsSetUp,
        tearDown=uploaderBugsTearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugtask-expiration.txt': LayeredDocFileSuite(
        '../doc/bugtask-expiration.txt',
        setUp=bugtaskExpirationSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugmessage.txt': LayeredDocFileSuite(
        '../doc/bugmessage.txt',
        id_extensions=['bugmessage.txt'],
        setUp=noPrivSetUp, tearDown=tearDown,
        layer=LaunchpadFunctionalLayer
        ),
    'bugmessage.txt-queued': LayeredDocFileSuite(
        '../doc/bugmessage.txt',
        id_extensions=['bugmessage.txt-queued'],
        setUp=uploadQueueSetUp,
        tearDown=uploadQueueTearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugmessage.txt-uploader': LayeredDocFileSuite(
        '../doc/bugmessage.txt',
        id_extensions=['bugmessage.txt-uploader'],
        setUp=uploaderSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugmessage.txt-checkwatches': LayeredDocFileSuite(
        '../doc/bugmessage.txt',
        id_extensions=['bugmessage.txt-checkwatches'],
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugtracker-person.txt': LayeredDocFileSuite(
        '../doc/bugtracker-person.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugwatch.txt':
        LayeredDocFileSuite(
        '../doc/bugwatch.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bug-watch-activity.txt':
        LayeredDocFileSuite(
        '../doc/bug-watch-activity.txt',
        setUp=checkwatchesSetUp, tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'bugtracker.txt':
        LayeredDocFileSuite(
        '../doc/bugtracker.txt',
        setUp=setUp, tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'checkwatches.txt':
        LayeredDocFileSuite(
        '../doc/checkwatches.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        stdout_logging_level=logging.WARNING,
        layer=LaunchpadZopelessLayer
        ),
    'checkwatches-cli-switches.txt':
        LayeredDocFileSuite(
        '../doc/checkwatches-cli-switches.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker.txt',
        setUp=setUp, tearDown=tearDown,
        stdout_logging_level=logging.WARNING,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-bug-imports.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-bug-imports.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-bugzilla.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-bugzilla.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-bugzilla-api.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-bugzilla-api.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-bugzilla-lp-plugin.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-bugzilla-lp-plugin.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-bugzilla-oddities.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-bugzilla-oddities.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-checkwatches.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-checkwatches.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-comment-imports.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-comment-imports.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-comment-pushing.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-comment-pushing.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-debbugs.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-debbugs.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-emailaddress.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-emailaddress.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-linking-back.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-linking-back.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        stdout_logging_level=logging.ERROR,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-mantis-csv.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-mantis-csv.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-mantis.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-mantis.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-roundup-python-bugs.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-roundup-python-bugs.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-roundup.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-roundup.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-rt.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-rt.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-sourceforge.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-sourceforge.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-trac.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-trac.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'externalbugtracker-trac-lp-plugin.txt':
        LayeredDocFileSuite(
        '../doc/externalbugtracker-trac-lp-plugin.txt',
        setUp=checkwatchesSetUp,
        tearDown=tearDown,
        layer=LaunchpadZopelessLayer
        ),
    'filebug-data-parser.txt': LayeredDocFileSuite(
        '../doc/filebug-data-parser.txt'),
    'product-update-remote-product.txt': LayeredDocFileSuite(
        '../doc/product-update-remote-product.txt',
        setUp=updateRemoteProductSetup,
        tearDown=updateRemoteProductTeardown,
        layer=LaunchpadZopelessLayer
        ),
    'product-update-remote-product-script.txt': LayeredDocFileSuite(
        '../doc/product-update-remote-product-script.txt',
        setUp=updateRemoteProductSetup,
        tearDown=updateRemoteProductTeardown,
        layer=LaunchpadZopelessLayer
        ),
    'sourceforge-remote-products.txt': LayeredDocFileSuite(
        '../doc/sourceforge-remote-products.txt',
        layer=LaunchpadZopelessLayer,
        ),
    'bug-set-status.txt-processmail': LayeredDocFileSuite(
        '../doc/bug-set-status.txt',
        id_extensions=['bug-set-status.txt-processmail'],
        setUp=bugSetStatusSetUp, tearDown=tearDown,
        layer=ProcessMailLayer,
        stdout_logging=False),
    'bugmessage.txt-processmail': LayeredDocFileSuite(
        '../doc/bugmessage.txt',
        id_extensions=['bugmessage.txt-processmail'],
        setUp=bugmessageSetUp, tearDown=tearDown,
        layer=ProcessMailLayer,
        stdout_logging=False),
    'bugs-emailinterface.txt-processmail': LayeredDocFileSuite(
        '../tests/bugs-emailinterface.txt',
        setUp=setUp, tearDown=tearDown,
        layer=ProcessMailLayer,
        stdout_logging=False),
    }


def test_suite():
    suite = unittest.TestSuite()

    stories_dir = os.path.join(os.path.pardir, 'stories')
    suite.addTest(PageTestSuite(stories_dir))
    stories_path = os.path.join(here, stories_dir)
    for story_dir in os.listdir(stories_path):
        full_story_dir = os.path.join(stories_path, story_dir)
        if not os.path.isdir(full_story_dir):
            continue
        story_path = os.path.join(stories_dir, story_dir)
        suite.addTest(PageTestSuite(story_path))

    testsdir = os.path.abspath(
        os.path.normpath(os.path.join(here, os.path.pardir, 'doc'))
        )

    # Add special needs tests
    for key, special_suite in sorted(special.items()):
        suite.addTest(special_suite)

    # Add tests using default setup/teardown
    filenames = [filename
                 for filename in os.listdir(testsdir)
                 if filename.endswith('.txt') and filename not in special]
    # Sort the list to give a predictable order.
    filenames.sort()
    for filename in filenames:
        path = os.path.join('../doc/', filename)
        one_test = LayeredDocFileSuite(
            path, setUp=setUp, tearDown=tearDown,
            layer=LaunchpadFunctionalLayer,
            stdout_logging_level=logging.WARNING
            )
        suite.addTest(one_test)

    return suite
