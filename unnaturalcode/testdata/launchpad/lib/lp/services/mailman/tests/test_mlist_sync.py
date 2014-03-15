# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Test the  mlist-sync script."""

__metaclass__ = type
__all__ = []

from contextlib import contextmanager
import os
import shutil
from subprocess import (
    PIPE,
    Popen,
    )
import tempfile

from Mailman import mm_cfg
from Mailman.MailList import MailList
from Mailman.Utils import list_names
from transaction import commit

from lp.services.config import config
from lp.services.database.interfaces import IStore
from lp.services.identity.model.emailaddress import EmailAddressSet
from lp.services.mailman.tests import MailmanTestCase
from lp.testing import person_logged_in
from lp.testing.layers import DatabaseFunctionalLayer


@contextmanager
def production_config(host_name):
    """Simulate a production Launchpad and mailman config."""
    config.push('production', """\
        [mailman]
        build_host_name: %s
        """ % host_name)
    default_email_host = mm_cfg.DEFAULT_EMAIL_HOST
    mm_cfg.DEFAULT_EMAIL_HOST = host_name
    default_url_host = mm_cfg.DEFAULT_URL_HOST
    mm_cfg.DEFAULT_URL_HOST = host_name
    try:
        yield
    finally:
        mm_cfg.DEFAULT_URL_HOST = default_url_host
        mm_cfg.DEFAULT_EMAIL_HOST = default_email_host
        config.pop('production')


class TestMListSync(MailmanTestCase):
    """Test mlist-sync script."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestMListSync, self).setUp()
        self.host_name = 'lists.production.launchpad.dev'
        with production_config(self.host_name):
            self.team = self.factory.makeTeam(name='team-1')
            self.mailing_list = self.factory.makeMailingList(
                self.team, self.team.teamowner)
            self.mm_list = self.makeMailmanList(self.mailing_list)
            self.mm_list.Unlock()
        self.addCleanup(self.cleanMailmanList, None, self.mm_list)
        archive_dir = os.path.join(mm_cfg.VAR_PREFIX, 'mhonarc')
        os.makedirs(os.path.join(archive_dir, self.team.name))
        self.addCleanup(shutil.rmtree, archive_dir, ignore_errors=True)
        self.naked_email_address_set = EmailAddressSet()

    def setupProductionFiles(self):
        "Setup a production file structure to sync."
        tempdir = tempfile.mkdtemp()
        source_dir = os.path.join(tempdir, 'production')
        shutil.copytree(
            config.mailman.build_var_dir, source_dir, symlinks=True)
        self.addCleanup(shutil.rmtree, source_dir, ignore_errors=True)
        return source_dir

    def runMListSync(self, source_dir):
        """Run mlist-sync.py."""
        store = IStore(self.team)
        store.flush()
        commit()
        store.invalidate()
        proc = Popen(
            ('scripts/mlist-sync.py', '--hostname',
             self.host_name, source_dir),
            stdout=PIPE, stderr=PIPE,
            cwd=config.root,
            env=dict(LPCONFIG=DatabaseFunctionalLayer.appserver_config_name))
        stdout, stderr = proc.communicate()
        return proc.returncode, stderr

    def getListInfo(self):
        """Return a list of 4-tuples of Mailman mailing list info."""
        list_info = []
        for list_name in sorted(list_names()):
            if list_name == mm_cfg.MAILMAN_SITE_LIST:
                continue
            mailing_list = MailList(list_name, lock=False)
            list_address = mailing_list.getListAddress()
            if self.naked_email_address_set.getByEmail(list_address) is None:
                email = '%s not found' % list_address
            else:
                email = list_address
            list_info.append(
                (mailing_list.internal_name(), mailing_list.host_name,
                 mailing_list.web_page_url, email))
        return list_info

    def test_staging_sync(self):
        # List is synced with updated URLs and email addresses.
        source_dir = self.setupProductionFiles()
        returncode, stderr = self.runMListSync(source_dir)
        self.assertEqual(0, returncode, stderr)
        list_summary = [(
            'team-1',
            'lists.launchpad.dev',
            'http://lists.launchpad.dev/mailman/',
            'team-1@lists.launchpad.dev')]
        self.assertEqual(list_summary, self.getListInfo())

    def test_staging_sync_list_without_team(self):
        # Lists without a team are not synced. This happens when a team
        # is deleted, but the list and archive remain.
        with production_config(self.host_name):
            mlist = self.makeMailmanListWithoutTeam('no-team', 'ex@eg.dom')
            mlist.Unlock()
            os.makedirs(os.path.join(
                mm_cfg.VAR_PREFIX, 'mhonarc', 'no-team'))
        self.addCleanup(self.cleanMailmanList, None, 'no-team')
        source_dir = self.setupProductionFiles()
        returncode, stderr = self.runMListSync(source_dir)
        self.assertEqual(0, returncode, stderr)
        list_summary = [(
            'team-1',
            'lists.launchpad.dev',
            'http://lists.launchpad.dev/mailman/',
            'team-1@lists.launchpad.dev')]
        self.assertEqual(list_summary, self.getListInfo())

    def test_staging_sync_with_team_address(self):
        # The team's other address is not updated by the sync process.
        email = self.factory.makeEmail('team-1@eg.dom', self.team)
        with production_config(self.host_name):
            self.team.setContactAddress(email)
        source_dir = self.setupProductionFiles()
        returncode, stderr = self.runMListSync(source_dir)
        self.assertEqual(0, returncode, stderr)
        list_summary = [(
            'team-1',
            'lists.launchpad.dev',
            'http://lists.launchpad.dev/mailman/',
            'team-1@lists.launchpad.dev')]
        self.assertEqual(list_summary, self.getListInfo())
        with person_logged_in(self.team.teamowner):
            self.assertEqual('team-1@eg.dom', self.team.preferredemail.email)
