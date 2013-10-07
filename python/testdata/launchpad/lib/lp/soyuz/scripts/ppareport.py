# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""PPA report tool

Generate several reports about the PPA repositories.

 * Over-quota
 * User's emails
 * Orphan repositories (requires access to the PPA host machine disk)
 * Missing repositories (requires access to the PPA host machine disk)
"""

import operator
import os
import sys

from storm.locals import Join
from storm.store import Store
from zope.component import getUtility

from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.model.person import (
    get_recipients,
    Person,
    )
from lp.services.config import config
from lp.services.propertycache import cachedproperty
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )
from lp.services.webapp import canonical_url
from lp.soyuz.enums import ArchivePurpose
from lp.soyuz.model.archive import Archive
from lp.soyuz.model.publishing import SourcePackagePublishingHistory


class PPAReportScript(LaunchpadScript):

    description = "PPA report tool."
    output = None

    def add_my_options(self):
        self.parser.add_option(
            '-p', '--ppa', dest='archive_owner_name', action='store',
            help='Archive owner name in case of PPA operations')

        self.parser.add_option(
            '-o', '--output', metavar='FILENAME', action='store',
            type='string', dest='output', default=None,
            help='Optional file to store output.')

        self.parser.add_option(
            '-t', '--quota-threshold', dest='quota_threshold',
            action='store', type=float, default=80,
            help='Quota threshold percentage, defaults to %default%')

        self.parser.add_option(
            '--gen-over-quota', action='store_true', default=False,
            help='Generate PPAs over-quota list.')

        self.parser.add_option(
            '--gen-user-emails', action='store_true', default=False,
            help='Generate active PPA user email list')

        self.parser.add_option(
            '--gen-orphan-repos', action='store_true', default=False,
            help='Generate PPAs orphan repositories list.')

        self.parser.add_option(
            '--gen-missing-repos', action='store_true', default=False,
            help='Generate PPAs missing repositories list.')

    @cachedproperty
    def ppas(self):
        """A cached tuple containing relevant PPAs objects for 'ubuntu'.

        if `self.options.archive_owner_name` is defined only return PPAs
        with matching owner names.
        """
        distribution = getUtility(IDistributionSet).getByName('ubuntu')
        store = Store.of(distribution)
        origin = [
            Archive,
            Join(SourcePackagePublishingHistory,
                 SourcePackagePublishingHistory.archive == Archive.id),
            ]
        clauses = [
            Archive.distribution == distribution,
            Archive.purpose == ArchivePurpose.PPA,
            Archive._enabled == True,
            ]

        owner_name = self.options.archive_owner_name
        if owner_name is not None:
            origin.append(Join(Person, Archive.owner == Person.id))
            clauses.append(Person.name == owner_name)

        results = store.using(*origin).find(
            Archive, *clauses)
        results.order_by(Archive.date_created)

        return tuple(results.config(distinct=True))

    def setOutput(self):
        """Set the output file descriptor.

        If the 'output' options was passed open a file named as its
        content, otherwise use `sys.stdout`.
        """
        if self.options.output is not None:
            self.logger.info('Report file: %s' % self.options.output)
            self.output = open(self.options.output, 'w')
        else:
            self.output = sys.stdout

    def closeOutput(self):
        """Closes the `output` file descriptor """
        self.output.close()

    def checkOptions(self):
        """Verify if the given command-line options are sane."""
        if ((self.options.gen_orphan_repos or
             self.options.gen_missing_repos or
             self.options.gen_over_quota) and
            self.options.gen_user_emails):
            raise LaunchpadScriptFailure(
                'Users-list cannot be combined with other reports.')

        if ((self.options.gen_orphan_repos or
             self.options.gen_missing_repos) and
            self.options.archive_owner_name is not None):
            raise LaunchpadScriptFailure(
                'Cannot calculate repository paths for a single PPA.')

        if ((self.options.gen_orphan_repos or
             self.options.gen_missing_repos) and
            not os.path.exists(config.personalpackagearchive.root)):
            raise LaunchpadScriptFailure(
                'Cannot access PPA root directory.')

    def main(self):
        self.checkOptions()

        self.logger.info('Considering %d active PPAs.' % len(self.ppas))

        self.setOutput()

        if self.options.gen_over_quota:
            self.reportOverQuota()

        if self.options.gen_user_emails:
            self.reportUserEmails()

        if self.options.gen_orphan_repos:
            self.reportOrphanRepos()

        if self.options.gen_missing_repos:
            self.reportMissingRepos()

        self.closeOutput()

        self.logger.info('Done')

    def reportOverQuota(self):
        self.output.write(
            '= PPAs over %.2f%% of their quota =\n' %
            self.options.quota_threshold)
        threshold = self.options.quota_threshold / 100.0
        for ppa in self.ppas:
            limit = ppa.authorized_size
            size = ppa.estimated_size / (2 ** 20)
            if size <= (threshold * limit):
                continue
            line = "%s | %d | %d\n" % (canonical_url(ppa), limit, size)
            self.output.write(line.encode('utf-8'))
        self.output.write('\n')

    def reportUserEmails(self):
        self.output.write('= PPA user emails =\n')
        people_to_email = set()
        for ppa in self.ppas:
            people_to_email.update(get_recipients(ppa.owner))
        sorted_people_to_email = sorted(
            people_to_email, key=operator.attrgetter('name'))
        for user in sorted_people_to_email:
            line = u"%s | %s | %s\n" % (
                user.name, user.displayname, user.preferredemail.email)
            self.output.write(line.encode('utf-8'))
        self.output.write('\n')

    @cachedproperty
    def expected_paths(self):
        """Frozenset containing the expected PPA repository paths."""
        return frozenset(ppa.owner.name for ppa in self.ppas)

    @cachedproperty
    def existing_paths(self):
        """Frozenset containing the existing PPA repository paths."""
        return frozenset(os.listdir(config.personalpackagearchive.root))

    def reportOrphanRepos(self):
        self.output.write('= Orphan PPA repositories =\n')
        orphan_paths = self.existing_paths - self.expected_paths
        for orphan in sorted(orphan_paths):
            repo_path = os.path.join(
                config.personalpackagearchive.root, orphan)
            self.output.write('%s\n' % repo_path)
        self.output.write('\n')

    def reportMissingRepos(self):
        self.output.write('= Missing PPA repositories =\n')
        missing_paths = self.expected_paths - self.existing_paths
        for missing in sorted(missing_paths):
            repo_path = os.path.join(
                config.personalpackagearchive.root, missing)
            self.output.write('%s\n' % repo_path)
        self.output.write('\n')
