# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from doctest import DocTestSuite
import unittest

from lp.services.mail.commands import (
    EmailCommand,
    EmailCommandCollection,
    )
from lp.testing import TestCase


class CommandOne(EmailCommand):
    pass


class CommandTwo(EmailCommand):
    case_insensitive_args = False


class SampleCommandCollection(EmailCommandCollection):
    _commands = {
        'one': CommandOne,
        'two': CommandTwo,
    }


class TestEmailCommandCollection(TestCase):
    def test_parsingParameters(self):
        self.assertEqual(
            {'one': True, 'two': False},
            SampleCommandCollection.parsingParameters())


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(DocTestSuite('lp.services.mail.commands'))
    suite.addTest(unittest.TestLoader().loadTestsFromName(__name__))
    return suite
