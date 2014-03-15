# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test cron script for processing jobs from any job source class."""

__metaclass__ = type

import transaction
from zope.component import getUtility

from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.services.config import config
from lp.services.scripts.tests import run_script
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadScriptLayer
from lp.testing.matchers import DocTestMatches


class ProcessJobSourceTest(TestCaseWithFactory):
    """Test the process-job-source.py script."""
    layer = LaunchpadScriptLayer
    script = 'cronscripts/process-job-source.py'

    def tearDown(self):
        super(ProcessJobSourceTest, self).tearDown()
        self.layer.force_dirty_database()

    def test_missing_argument(self):
        # The script should display usage info when called without any
        # arguments.
        returncode, output, error = run_script(
            self.script, [], expect_returncode=1)
        self.assertIn('Usage:', output)
        self.assertIn('process-job-source.py [options] JOB_SOURCE', output)

    def test_empty_queue(self):
        # The script should just create a lockfile and exit if no jobs
        # are in the queue.
        returncode, output, error = run_script(
            self.script, ['IMembershipNotificationJobSource'])
        expected = (
            'INFO    Creating lockfile: .*launchpad-process-job-'
            'source-IMembershipNotificationJobSource.lock.*')
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, error)

    def test_processed(self):
        # The script should output the number of jobs it processed.
        person = self.factory.makePerson(name='murdock')
        team = self.factory.makeTeam(name='a-team')
        login_person(team.teamowner)
        team.addMember(person, team.teamowner)
        membership_set = getUtility(ITeamMembershipSet)
        tm = membership_set.getByPersonAndTeam(person, team)
        tm.setStatus(TeamMembershipStatus.ADMIN, team.teamowner)
        transaction.commit()
        returncode, output, error = run_script(
            self.script, ['-v', 'IMembershipNotificationJobSource'])
        self.assertIn(
            ('INFO    Running <MembershipNotificationJob '
             'about ~murdock in ~a-team; status=Waiting>'),
            error)
        self.assertIn('DEBUG   MembershipNotificationJob sent email', error)
        self.assertIn('Ran 1 MembershipNotificationJob jobs.', error)


class ProcessJobSourceGroupsTest(TestCaseWithFactory):
    """Test the process-job-source-groups.py script."""
    layer = LaunchpadScriptLayer
    script = 'cronscripts/process-job-source-groups.py'

    def getJobSources(self, *groups):
        sources = config['process-job-source-groups'].job_sources
        sources = (source.strip() for source in sources.split(','))
        sources = (source for source in sources if source in config)
        if len(groups) != 0:
            sources = (
                source for source in sources
                if config[source].crontab_group in groups)
        return sorted(set(sources))

    def tearDown(self):
        super(ProcessJobSourceGroupsTest, self).tearDown()
        self.layer.force_dirty_database()

    def test_missing_argument(self):
        # The script should display usage info when called without any
        # arguments.
        returncode, output, error = run_script(
            self.script, [], expect_returncode=1)
        self.assertIn(
            ('Usage: process-job-source-groups.py '
             '[ -e JOB_SOURCE ] GROUP [GROUP]...'),
            output)
        self.assertIn('-e JOB_SOURCE, --exclude=JOB_SOURCE', output)
        self.assertIn('At least one group must be specified.', output)
        self.assertIn('Group: MAIN\n    I', output)

    def test_empty_queue(self):
        # The script should just launch a child for each job source class,
        # and then exit if no jobs are in the queue.  It should not create
        # its own lockfile.
        returncode, output, error = run_script(self.script, ['MAIN'])
        expected = (
            '.*Creating lockfile:.*launchpad-process-job-'
            'source-IMembershipNotificationJobSource.lock.*')
        self.assertTextMatchesExpressionIgnoreWhitespace(expected, error)
        self.assertNotIn("launchpad-processjobsourcegroups.lock", error)

    def test_processed(self):
        # The script should output the number of jobs that have been
        # processed by its child processes.
        person = self.factory.makePerson(name='murdock')
        team = self.factory.makeTeam(name='a-team')
        login_person(team.teamowner)
        team.addMember(person, team.teamowner)
        membership_set = getUtility(ITeamMembershipSet)
        tm = membership_set.getByPersonAndTeam(person, team)
        tm.setStatus(TeamMembershipStatus.ADMIN, team.teamowner)
        transaction.commit()
        returncode, output, error = run_script(
            self.script, ['-v', '--wait', 'MAIN'])
        self.assertTextMatchesExpressionIgnoreWhitespace(
            ('INFO Running <MembershipNotificationJob '
             'about ~murdock in ~a-team; status=Waiting>'),
            error)
        self.assertIn('DEBUG   MembershipNotificationJob sent email', error)
        self.assertIn('Ran 1 MembershipNotificationJob jobs.', error)

    def test_exclude(self):
        # Job sources can be excluded with a --exclude switch.
        args = ["MAIN"]
        for source in self.getJobSources("MAIN"):
            args.extend(("--exclude", source))
        returncode, output, error = run_script(self.script, args)
        self.assertEqual("", error)

    def test_exclude_non_existing_group(self):
        # If a job source specified by --exclude does not exist the script
        # continues, logging a short info message about it.
        args = ["MAIN"]
        for source in self.getJobSources("MAIN"):
            args.extend(("--exclude", source))
        args.extend(("--exclude", "BobbyDazzler"))
        returncode, output, error = run_script(self.script, args)
        expected = "INFO    'BobbyDazzler' is not in MAIN\n"
        self.assertThat(error, DocTestMatches(expected))
