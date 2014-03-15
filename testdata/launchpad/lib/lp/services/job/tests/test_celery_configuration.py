# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from contextlib import contextmanager

from lp.services.config import config
from lp.testing import TestCase
from lp.testing.layers import RabbitMQLayer


@contextmanager
def changed_config(changes):
    config.push('test_changes', changes)
    yield
    config.pop('test_changes')


class TestCeleryConfiguration(TestCase):
    layer = RabbitMQLayer

    def check_default_common_parameters(self, config):
        # Tests for default config values that are set for app servers
        # and for celeryd instances.

        # Four queues are defined; the binding key for each queue is
        # just the queue name.
        queue_names = [
            'branch_write_job', 'branch_write_job_slow',
            'bzrsyncd_job', 'bzrsyncd_job_slow', 'celerybeat',
            'launchpad_job', 'launchpad_job_slow']
        queues = config['CELERY_QUEUES']
        self.assertEqual(queue_names, sorted(queues))
        for name in queue_names:
            self.assertEqual(name, queues[name]['binding_key'])

        self.assertEqual('localhost', config['BROKER_HOST'])
        # BROKER_PORT changes between test runs, so just check that it
        # is defined.
        self.assertTrue('BROKER_PORT' in config)
        self.assertEqual('guest', config['BROKER_USER'])
        self.assertEqual('guest', config['BROKER_PASSWORD'])
        self.assertEqual('/', config['BROKER_VHOST'])
        self.assertFalse(config['CELERY_CREATE_MISSING_QUEUES'])
        self.assertEqual('job', config['CELERY_DEFAULT_EXCHANGE'])
        self.assertEqual('launchpad_job', config['CELERY_DEFAULT_QUEUE'])
        self.assertEqual(
            ('lp.services.job.celeryjob', ), config['CELERY_IMPORTS'])
        self.assertEqual('amqp', config['CELERY_RESULT_BACKEND'])

    def test_app_server_configuration(self):
        from lp.services.job.celeryconfig import configure
        config = configure([''])
        self.check_default_common_parameters(config)

    def check_job_specific_celeryd_configuration(self, expected, config):
        self.check_default_common_parameters(config)
        self.assertEqual(
            expected['concurrency'], config['CELERYD_CONCURRENCY'])
        self.assertEqual(
            expected['timeout'], config['CELERYD_TASK_SOFT_TIME_LIMIT'])
        self.assertEqual(
            expected['fallback'], config.get('FALLBACK', None))

    def test_default_celeryd_configuration_fast_lanes(self):
        from lp.services.job.celeryconfig import configure
        expected = {
            'concurrency': 3,
            'fallback': 'launchpad_job_slow',
            'timeout': 300,
            }
        config = configure(['celeryd', '-Q', 'launchpad_job'])
        self.check_default_common_parameters(config)
        self.check_job_specific_celeryd_configuration(expected, config)
        config = configure(['celeryd', '-Q', 'branch_write_job'])
        self.check_default_common_parameters(config)
        expected['fallback'] = 'branch_write_job_slow'
        self.check_job_specific_celeryd_configuration(expected, config)

    def test_default_celeryd_configuration_slow_lanes(self):
        from lp.services.job.celeryconfig import configure
        expected = {
            'concurrency': 1,
            'fallback': None,
            'timeout': 86400,
            }
        config = configure(['celeryd', '-Q', 'launchpad_job_slow'])
        self.check_default_common_parameters(config)
        self.check_job_specific_celeryd_configuration(expected, config)
        config = configure(['celeryd', '-Q', 'branch_write_job_slow'])
        self.check_default_common_parameters(config)
        self.check_job_specific_celeryd_configuration(expected, config)

    def test_circular_fallback_lanes(self):
        # Circular fallback lanes are detected.
        # Import late because the RabbitMQ parameters are set during layer
        # setup.
        from lp.services.job.celeryconfig import (
            ConfigurationError,
            configure,
            )
        with changed_config(
            """
            [launchpad_job_slow]
            fallback_queue: launchpad_job
        """):
            error = (
                "Circular chain of fallback queues: launchpad_job already in "
                "['launchpad_job', 'launchpad_job_slow']"
                )
            self.assertRaisesWithContent(
                ConfigurationError, error, configure, [''])

    def test_missing_queue_parameter_for_celeryd(self):
        # An exception is raised when celeryd is started without
        # the parameter -Q.
        # Import late because the RabbitMQ parameters are set during layer
        # setup.
        from lp.services.job.celeryconfig import (
            ConfigurationError,
            configure,
            )
        error = 'A queue must be specified.'
        self.assertRaisesWithContent(
            ConfigurationError, error, configure, ['celeryd'])

    def test_two_queues_for_celeryd(self):
        # An exception is raised when celeryd is started for two queues.
        # Import late because the RabbitMQ parameters are set during layer
        # setup.
        from lp.services.job.celeryconfig import (
            ConfigurationError,
            configure,
            )
        error = 'A celeryd instance may serve only one queue.'
        self.assertRaisesWithContent(
            ConfigurationError, error, configure,
            ['celeryd', '--queue=launchpad_job,branch_write_job'])

    def test_unconfigured_queue_for_celeryd(self):
        # An exception is raised when celeryd is started for a queue that
        # is not configured.
        # Import late because the RabbitMQ parameters are set during layer
        # setup.
        from lp.services.job.celeryconfig import (
            ConfigurationError,
            configure,
            )
        error = 'Queue foo is not configured in schema-lazr.conf'
        self.assertRaisesWithContent(
            ConfigurationError, error, configure, ['celeryd', '--queue=foo'])
