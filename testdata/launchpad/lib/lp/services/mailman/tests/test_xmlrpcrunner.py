# Copyright 20011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the Launchpad XMLRPC runner."""

__metaclass__ = type
__all__ = []

from contextlib import contextmanager
from datetime import datetime
import os
import socket
import tarfile

from Mailman import (
    Errors,
    MailList,
    mm_cfg,
    )
from Mailman.Logging.Syslog import syslog
from Mailman.Queue.XMLRPCRunner import (
    handle_proxy_error,
    XMLRPCRunner,
    )
from Mailman.Utils import list_names
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.registry.interfaces.mailinglist import (
    IMailingListSet,
    MailingListStatus,
    )
from lp.services.config import config
from lp.services.mailman.monkeypatches.xmlrpcrunner import (
    get_mailing_list_api_proxy,
    )
from lp.services.mailman.tests import (
    get_mailing_list_api_test_proxy,
    MailmanTestCase,
    )
from lp.services.xmlrpc import Transport
from lp.testing import (
    monkey_patch,
    person_logged_in,
    TestCase,
    )
from lp.testing.fixture import CaptureOops
from lp.testing.layers import (
    BaseLayer,
    DatabaseFunctionalLayer,
    )


@contextmanager
def one_loop_exception(runner):
    """Raise an error during th execution of _oneloop.

    This function replaces _check_list_actions() with a function that
    raises an error. _oneloop() handles the exception.
    """

    def raise_exception():
        raise Exception('Test exception handling.')

    original__check_list_actions = runner._check_list_actions
    runner._check_list_actions = raise_exception
    try:
        yield
    finally:
        runner._check_list_actions = original__check_list_actions


class TestXMLRPCRunnerTimeout(TestCase):
    """Make sure that we set a timeout on our xmlrpc connections."""

    layer = BaseLayer

    def test_timeout_used(self):
        proxy = get_mailing_list_api_proxy()
        # We don't want to trigger the proxy if we misspell something, so we
        # look in the dict.
        transport = proxy.__dict__['_ServerProxy__transport']
        self.assertTrue(isinstance(transport, Transport))
        self.assertEqual(mm_cfg.XMLRPC_TIMEOUT, transport.timeout)
        # This is a bit rickety--if the mailman config was built under a
        # different instance that has a different timeout value, this will
        # fail.  Removing this next assertion would probably be OK then, but
        # I think it is nice to have.
        self.assertEqual(config.mailman.xmlrpc_timeout, mm_cfg.XMLRPC_TIMEOUT)


class TestXMLRPCRunnerHeatBeat(MailmanTestCase):
    """Test XMLRPCRunner._hearbeat method."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestXMLRPCRunnerHeatBeat, self).setUp()
        self.mm_list = None
        syslog.write_ex('xmlrpc', 'Ensure the log is open.')
        self.reset_log()
        self.runner = XMLRPCRunner()
        # MailmanTestCase's setup of the test proxy is ignored because
        # the runner had a reference to the true proxy in its __init__.
        self.runner._proxy = get_mailing_list_api_test_proxy()

    def test_heartbeat_on_start(self):
        # A heartbeat is recorded in the log on start.
        mark = self.get_mark()
        self.assertTrue(mark is not None)

    def test_heatbeat_frequency_no_heartbeat(self):
        # A heartbeat is not recorded when the that last beat less than
        # the heartbeat_frequency.
        self.runner._heartbeat()
        self.reset_log()
        self.runner._heartbeat()
        now = datetime.now()
        last_heartbeat = self.runner.last_heartbeat
        self.assertTrue(
            now - last_heartbeat < self.runner.heartbeat_frequency)
        mark = self.get_mark()
        self.assertTrue(mark is None)

    def test__oneloop_success_heartbeat(self):
        # A heartbeat is recorded when the loop completes successfully.
        self.reset_log()
        self.runner.last_heartbeat = (
            self.runner.last_heartbeat - self.runner.heartbeat_frequency)
        self.runner._oneloop()
        mark = self.get_mark()
        self.assertTrue(mark is not None)

    def test__oneloop_exception_no_heartbeat(self):
        # A heartbeat is not recorded when there is an exception in the loop.
        self.reset_log()
        self.runner.last_heartbeat = (
            self.runner.last_heartbeat - self.runner.heartbeat_frequency)
        # Hack runner to raise an oops.
        with one_loop_exception(self.runner):
            self.runner._oneloop()
        mark = self.get_mark()
        self.assertTrue(mark is None)


class TestHandleProxyError(MailmanTestCase):
    """Test XMLRPCRunner.handle_proxy_error function."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestHandleProxyError, self).setUp()
        self.team, self.mailing_list = self.factory.makeTeamAndMailingList(
            'team-1', 'team-1-owner')
        self.mm_list = self.makeMailmanList(self.mailing_list)
        syslog.write_ex('xmlrpc', 'Ensure the log is open.')
        self.reset_log()

    def test_communication_log_entry(self):
        # Connection errors are reported in the log.
        error = socket.error('Testing socket error.')
        handle_proxy_error(error)
        mark = self.get_log_entry('Cannot talk to Launchpad:')
        self.assertTrue(mark is not None)

    def test_fault_log_entry(self):
        # Fault errors are reported in the log.
        error = Exception('Testing generic error.')
        handle_proxy_error(error)
        mark = self.get_log_entry('Launchpad exception:')
        self.assertTrue(mark is not None)

    def test_message_raises_discard_message_error(self):
        # When message is passed to the function, DiscardMessage is raised
        # and the message is re-enqueued in the incoming queue.
        error = Exception('Testing generic error.')
        msg = self.makeMailmanMessage(
            self.mm_list, 'lost@noplace.dom', 'subject', 'any content.')
        msg_data = {}
        self.assertRaises(
            Errors.DiscardMessage, handle_proxy_error, error, msg, msg_data)
        self.assertIsEnqueued(msg)


class OopsReportingTestCase(MailmanTestCase):
    """Test XMLRPCRunner reports oopses."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(OopsReportingTestCase, self).setUp()
        self.mm_list = None
        syslog.write_ex('xmlrpc', 'Ensure the log is open.')
        self.reset_log()
        self.runner = XMLRPCRunner()
        # MailmanTestCase's setup of the test proxy is ignored because
        # the runner had a reference to the true proxy in its __init__.
        self.runner._proxy = get_mailing_list_api_test_proxy()

    def test_oops_reporting(self):
        capture = CaptureOops()
        capture.setUp()
        with one_loop_exception(self.runner):
            self.runner._oneloop()
        oops = capture.oopses[0]
        capture.cleanUp()
        self.assertEqual('T-mailman', oops['reporter'])
        self.assertTrue(oops['id'].startswith('OOPS-'))
        self.assertEqual('Exception', oops['type'])
        self.assertEqual('Test exception handling.', oops['value'])
        self.assertTrue(
            oops['tb_text'].startswith('Traceback (most recent call last):'))


@contextmanager
def locked_list(mm_list):
    """Ensure a lock is not held."""
    mm_list.Lock()
    try:
        yield
    finally:
        mm_list.Unlock()


class OneLoopTestCase(MailmanTestCase):
    """Test XMLRPCRunner._oneloop method.

    The _oneloop() method calls all the methods used to sync Lp to Mailman.
    """

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(OneLoopTestCase, self).setUp()
        self.mm_list = None
        self.runner = XMLRPCRunner()
        # MailmanTestCase's setup of the test proxy is ignored because
        # the runner had a reference to the true proxy in its __init__.
        self.runner._proxy = get_mailing_list_api_test_proxy()

    def makeTeamList(self, team_name, owner_name, need_mm_list=True):
        team, mailing_list = self.factory.makeTeamAndMailingList(
            team_name, owner_name)
        if need_mm_list:
            self.mm_list = self.makeMailmanList(mailing_list)
            self.mm_list.Unlock()
        return team, mailing_list

    def test_create(self):
        # Lists are created in mailman after they are created in Lp.
        team = self.factory.makeTeam(name='team-1')
        # The factory cannot be used because it forces the list into a
        # usable state.
        mailing_list = getUtility(IMailingListSet).new(team, team.teamowner)
        self.runner._oneloop()
        self.assertContentEqual(
            [mm_cfg.MAILMAN_SITE_LIST, 'team-1'], list_names())
        mm_list = MailList.MailList('team-1')
        self.addCleanup(self.cleanMailmanList, mm_list)
        self.assertEqual(
            'team-1@lists.launchpad.dev', mm_list.getListAddress())
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_deactivate(self):
        # Lists are deactivted in mailman after they are deactivate in Lp.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        mailing_list.deactivate()
        self.runner._oneloop()
        self.assertContentEqual([mm_cfg.MAILMAN_SITE_LIST], list_names())
        backup_file = os.path.join(mm_cfg.VAR_PREFIX, 'backups', 'team-1.tgz')
        self.assertTrue(os.path.exists(backup_file))
        tarball = tarfile.open(backup_file, 'r:gz')
        content = ['team-1', 'team-1/config.pck']
        self.assertContentEqual(content, tarball.getnames())
        self.assertEqual(MailingListStatus.INACTIVE, mailing_list.status)

    def test_modify(self):
        # Lists are modified in mailman after they are modified in Lp.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        with person_logged_in(team.teamowner):
            mailing_list.welcome_message = 'hello'
        self.assertEqual(MailingListStatus.MODIFIED, mailing_list.status)
        self.runner._oneloop()
        self.mm_list.Load()
        self.assertEqual('hello', self.mm_list.welcome_msg)
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_reactivate(self):
        # Lists are deactivted in mailman after they are deactivate in Lp.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        mailing_list.deactivate()
        self.runner._oneloop()
        backup_file = os.path.join(mm_cfg.VAR_PREFIX, 'backups', 'team-1.tgz')
        self.assertTrue(os.path.exists(backup_file))
        mailing_list.reactivate()
        self.runner._oneloop()
        self.assertFalse(os.path.exists(backup_file))
        self.assertEqual(
            'team-1@lists.launchpad.dev', self.mm_list.getListAddress())
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_get_subscriptions_add(self):
        # List members are added in mailman after they are subscribed in Lp.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        with person_logged_in(lp_user):
            # The factory person has auto join mailing list enabled.
            lp_user.join(team)
        self.runner._oneloop()
        with locked_list(self.mm_list):
            self.assertEqual(1, self.mm_list.isMember(lp_user_email))

    def test_get_subscriptions_add_alternate(self):
        # List members can have alternate addresses provided by Lp..
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        alt_email = self.factory.makeEmail('bat@eg.dom', person=lp_user)
        with person_logged_in(lp_user):
            lp_user.join(team)
            mailing_list.unsubscribe(lp_user)
            mailing_list.subscribe(lp_user, alt_email)
        self.runner._oneloop()
        with locked_list(self.mm_list):
            self.assertEqual(1, self.mm_list.isMember('bat@eg.dom'))

    def test_get_subscriptions_leave_team(self):
        # List members are removed when the leave the team.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        with person_logged_in(lp_user):
            lp_user.join(team)
        self.runner._oneloop()
        with person_logged_in(lp_user):
            lp_user.leave(team)
        self.runner._oneloop()
        with locked_list(self.mm_list):
            self.assertEqual(0, self.mm_list.isMember('albatros@eg.dom'))

    def test_get_subscriptions_rejoin_team(self):
        # Former list members are restored when they rejoin the team.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        with person_logged_in(lp_user):
            lp_user.join(team)
        self.runner._oneloop()
        with person_logged_in(lp_user):
            lp_user.leave(team)
        self.runner._oneloop()
        with person_logged_in(lp_user):
            lp_user.join(team)
        self.runner._oneloop()
        with locked_list(self.mm_list):
            self.assertEqual(1, self.mm_list.isMember('albatros@eg.dom'))

    def test_get_subscriptions_batching(self):
        # get_subscriptions iterates over batches of lists.
        config.push('batching test',
            """
            [mailman]
            subscription_batch_size: 1
            """)
        self.addCleanup(config.pop, 'batching test')
        team_1, mailing_list_1 = self.makeTeamList('team-1', 'owner-1')
        mm_list_1 = self.mm_list
        team_2, mailing_list_2 = self.makeTeamList('team-2', 'owner-2')
        mm_list_2 = self.mm_list
        self.addCleanup(self.cleanMailmanList, mm_list_1)
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        with person_logged_in(lp_user):
            # The factory person has auto join mailing list enabled.
            lp_user.join(team_1)
            lp_user.join(team_2)
        self.runner._oneloop()
        with locked_list(mm_list_1):
            self.assertEqual(1, mm_list_1.isMember(lp_user_email))
        with locked_list(mm_list_2):
            self.assertEqual(1, mm_list_2.isMember(lp_user_email))

    def test_get_subscriptions_shortcircut(self):
        # The method exist earlty without completing the update when
        # the runner is stopping.
        team, mailing_list = self.makeTeamList('team-1', 'owner-1')
        lp_user_email = 'albatros@eg.dom'
        lp_user = self.factory.makePerson(name='albatros', email=lp_user_email)
        with person_logged_in(lp_user):
            # The factory person has auto join mailing list enabled.
            lp_user.join(team)
        self.runner.stop()
        self.runner._get_subscriptions()
        with locked_list(self.mm_list):
            self.assertEqual(0, self.mm_list.isMember(lp_user_email))

    def test_constructing_to_active_recovery(self):
        # Lp is informed of the active list if it wrongly believes it is
        # being constructed.
        team = self.factory.makeTeam(name='team-1')
        mailing_list = getUtility(IMailingListSet).new(team, team.teamowner)
        self.addCleanup(self.cleanMailmanList, None, 'team-1')
        self.runner._oneloop()
        removeSecurityProxy(mailing_list).status = (
            MailingListStatus.CONSTRUCTING)
        self.runner._oneloop()
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_nonexistent_to_active_recovery(self):
        # Mailman will build the list if Lp thinks it is exists in the
        # CONSTRUCTING state
        team = self.factory.makeTeam(name='team-1')
        mailing_list = getUtility(IMailingListSet).new(team, team.teamowner)
        removeSecurityProxy(mailing_list).status = (
            MailingListStatus.CONSTRUCTING)
        self.runner._oneloop()
        self.assertContentEqual(
            [mm_cfg.MAILMAN_SITE_LIST, 'team-1'], list_names())
        mm_list = MailList.MailList('team-1')
        self.addCleanup(self.cleanMailmanList, mm_list)
        self.assertEqual(
            'team-1@lists.launchpad.dev', mm_list.getListAddress())
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_updating_to_active_recovery(self):
        # Lp is informed of the active list if it wrongly believes it is
        # being updated.
        team = self.factory.makeTeam(name='team-1')
        mailing_list = getUtility(IMailingListSet).new(team, team.teamowner)
        self.addCleanup(self.cleanMailmanList, None, 'team-1')
        self.runner._oneloop()
        removeSecurityProxy(mailing_list).status = (
            MailingListStatus.UPDATING)
        self.runner._oneloop()
        self.assertEqual(MailingListStatus.ACTIVE, mailing_list.status)

    def test_shortcircuit(self):
        # Oneloop will exit early if the runner is stopping.
        class State:

            def __init__(self):
                self.checked = None

        shortcircut = State()

        def fake_called():
            shortcircut.checked = False

        def fake_stop():
            shortcircut.checked = True
            self.runner.stop()

        with monkey_patch(self.runner,
                _check_list_actions=fake_stop, _get_subscriptions=fake_called):
            self.runner._oneloop()
            self.assertTrue(self.runner._shortcircuit())
            self.assertTrue(shortcircut.checked)
