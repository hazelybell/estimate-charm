# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests of the config fixtures."""

__metaclass__ = type

from testtools import TestCase

from lp.services.config import config
from lp.services.config.fixture import (
    ConfigFixture,
    ConfigUseFixture,
    )


class TestConfigUseFixture(TestCase):

    def test_sets_restores_instance(self):
        fixture = ConfigUseFixture('foo')
        orig_instance = config.instance_name
        fixture.setUp()
        try:
            self.assertEqual('foo', config.instance_name)
        finally:
            fixture.cleanUp()
        self.assertEqual(orig_instance, config.instance_name)


class TestConfigFixture(TestCase):

    def test_copies_and_derives(self):
        fixture = ConfigFixture('testtestconfig', 'testrunner')
        to_copy = [
            'launchpad.conf',
            'test-process-lazr.conf',
            ]
        fixture.setUp()
        try:
            for base in to_copy:
                path = 'configs/testtestconfig/' + base
                source = 'configs/testrunner/' + base
                old = open(source, 'rb').read()
                new = open(path, 'rb').read()
                self.assertEqual(old, new)
            confpath = 'configs/testtestconfig/launchpad-lazr.conf'
            lazr_config = open(confpath, 'rb').read()
            self.assertEqual(
                "[meta]\n"
                "extends: ../testrunner/launchpad-lazr.conf",
                lazr_config.strip())
        finally:
            fixture.cleanUp()
