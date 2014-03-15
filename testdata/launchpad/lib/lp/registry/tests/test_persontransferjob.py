# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for PersonTransferJobs."""

__metaclass__ = type

from lp.registry.enums import PersonTransferJobType
from lp.registry.model.persontransferjob import (
    PersonTransferJob,
    PersonTransferJobDerived,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class PersonTransferJobTestCase(TestCaseWithFactory):
    """Test case for basic PersonTransferJob class."""

    layer = LaunchpadZopelessLayer

    def test_instantiate(self):
        # PersonTransferJob.__init__() instantiates a
        # PersonTransferJob instance.
        person = self.factory.makePerson()
        team = self.factory.makeTeam()

        metadata = ('some', 'arbitrary', 'metadata')
        person_transfer_job = PersonTransferJob(
            person,
            team,
            PersonTransferJobType.MEMBERSHIP_NOTIFICATION,
            metadata)

        self.assertEqual(person, person_transfer_job.minor_person)
        self.assertEqual(team, person_transfer_job.major_person)
        self.assertEqual(
            PersonTransferJobType.MEMBERSHIP_NOTIFICATION,
            person_transfer_job.job_type)

        # When we actually access the PersonTransferJob's metadata it
        # gets unserialized from JSON, so the representation returned by
        # person_transfer_job.metadata will be different from what we
        # originally passed in.
        metadata_expected = [u'some', u'arbitrary', u'metadata']
        self.assertEqual(metadata_expected, person_transfer_job.metadata)


class PersonTransferJobDerivedTestCase(TestCaseWithFactory):
    """Test case for the PersonTransferJobDerived class."""

    layer = LaunchpadZopelessLayer

    def test_create_explodes(self):
        # PersonTransferJobDerived.create() will blow up because it
        # needs to be subclassed to work properly.
        person = self.factory.makePerson()
        team = self.factory.makeTeam()
        metadata = {'foo': 'bar'}
        self.assertRaises(
            AttributeError,
            PersonTransferJobDerived.create, person, team, metadata)
