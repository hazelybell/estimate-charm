# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test helpers for mailman integration."""

__metaclass__ = type
__all__ = []

from contextlib import contextmanager
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import shutil

from Mailman import (
    MailList,
    Message,
    mm_cfg,
    )
from Mailman.Logging.Syslog import syslog
from Mailman.Queue import XMLRPCRunner
from Mailman.Queue.sbcache import get_switchboard
from zope.security.proxy import removeSecurityProxy

from lp.registry.tests.mailinglists_helper import MailingListXMLRPCTestProxy
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


def get_mailing_list_api_test_proxy():
    return MailingListXMLRPCTestProxy(context=None, request=None)


@contextmanager
def fake_mailinglist_api_proxy():
    original_get_proxy = XMLRPCRunner.get_mailing_list_api_proxy
    XMLRPCRunner.get_mailing_list_api_proxy = get_mailing_list_api_test_proxy
    try:
        yield
    finally:
        XMLRPCRunner.get_mailing_list_api_proxy = original_get_proxy


class MailmanTestCase(TestCaseWithFactory):
    """TestCase with factory and mailman support."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailmanTestCase, self).setUp()
        # Replace the xmlrpc proxy with a fast wrapper of the real view.
        self.useContext(fake_mailinglist_api_proxy())

    def tearDown(self):
        super(MailmanTestCase, self).tearDown()
        self.cleanMailmanList(self.mm_list)

    def makeMailmanList(self, lp_mailing_list):
        team = lp_mailing_list.team
        owner_email = removeSecurityProxy(team.teamowner).preferredemail.email
        return self.makeMailmanListWithoutTeam(team.name, owner_email)

    def makeMailmanListWithoutTeam(self, list_name, owner_email):
        # This utility is based on mailman/tests/TestBase.py.
        self.cleanMailmanList(None, list_name)
        mlist = MailList.MailList()
        mlist.Create(list_name, owner_email, 'password')
        mlist.host_name = mm_cfg.DEFAULT_URL_HOST
        mlist.web_page_url = 'http://%s/mailman/' % mm_cfg.DEFAULT_URL_HOST
        mlist.personalize = 1
        mlist.include_rfc2369_headers = False
        mlist.use_dollar_strings = True
        mlist.Save()
        mlist.addNewMember(owner_email)
        return mlist

    def cleanMailmanList(self, mlist, list_name=None):
        # This utility is based on mailman/tests/TestBase.py.
        if mlist is not None:
            mlist.Unlock()
            list_name = mlist.internal_name()
        paths = [
            'lists/%s',
            'archives/private/%s',
            'archives/private/%s.mbox',
            'archives/public/%s',
            'archives/public/%s.mbox',
            'mhonarc/%s',
            ]
        for dirtmpl in paths:
            list_dir = os.path.join(mm_cfg.VAR_PREFIX, dirtmpl % list_name)
            if os.path.islink(list_dir):
                os.unlink(list_dir)
            elif os.path.isdir(list_dir):
                shutil.rmtree(list_dir, ignore_errors=True)

    def makeMailmanMessage(self, mm_list, sender, subject, content,
                           mime_type='plain', attachment=None):
        # Make a Mailman Message.Message.
        if isinstance(sender, (list, tuple)):
            sender = ', '.join(sender)
        message = MIMEMultipart()
        message['from'] = sender
        message['to'] = mm_list.getListAddress()
        message['subject'] = subject
        message['message-id'] = self.getUniqueString()
        message.attach(MIMEText(content, mime_type))
        if attachment is not None:
            # Rewrap the text message in a multipart message and add the
            # attachment.
            message.attach(attachment)
        mm_message = email.message_from_string(
            message.as_string(), Message.Message)
        return mm_message

    def get_log_entry(self, match_text):
        """Return the first matched text line found in the log."""
        log_path = syslog._logfiles['xmlrpc']._Logger__filename
        mark = None
        with open(log_path, 'r') as log_file:
            for line in log_file.readlines():
                if match_text in line:
                    mark = line
                    break
        return mark

    def get_mark(self):
        """Return the --MARK-- entry from the log or None."""
        return self.get_log_entry('--MARK--')

    def reset_log(self):
        """Truncate the log."""
        log_path = syslog._logfiles['xmlrpc']._Logger__filename
        syslog._logfiles['xmlrpc'].close()
        with open(log_path, 'w') as log_file:
            log_file.truncate()
        syslog.write_ex('xmlrpc', 'Reset by test.')

    def assertIsEnqueued(self, msg):
        """Assert the message was appended to the incoming queue."""
        switchboard = get_switchboard(mm_cfg.INQUEUE_DIR)
        file_path = switchboard.files()[-1]
        queued_msg, queued_msg_data = switchboard.dequeue(file_path)
        self.assertEqual(msg['message-id'], queued_msg['message-id'])

    @contextmanager
    def raise_proxy_exception(self, method_name):
        """Raise an exception when calling the passed proxy method name."""

        def raise_exception(*args):
            raise Exception('Test exception handling.')

        proxy = XMLRPCRunner.get_mailing_list_api_proxy()
        original_method = getattr(proxy.__class__, method_name)
        setattr(proxy.__class__, method_name, raise_exception)
        try:
            yield
        finally:
            setattr(proxy.__class__, method_name, original_method)
