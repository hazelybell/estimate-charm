# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from datetime import timedelta
import sys

import argparse

from lp.services.config import config


class ConfigurationError(Exception):
    """Errors raised due to misconfiguration."""


def check_circular_fallbacks(queue):
    """Check for curcular fallback queues.

    A circular chain of fallback queues could keep a job forever queued
    if it times out in all queues.
    """
    linked_queues = []
    while config[queue].fallback_queue != '':
        linked_queues.append(queue)
        queue = config[queue].fallback_queue
        if queue in linked_queues:
            raise ConfigurationError(
                'Circular chain of fallback queues: '
                '%s already in %s' % (queue, linked_queues))


def configure(argv):
    """Set the Celery parameters.

    Doing this in a function is convenient for testing.
    """
    result = {}
    CELERY_BEAT_QUEUE = 'celerybeat'
    celery_queues = {}
    queue_names = config.job_runner_queues.queues
    queue_names = queue_names.split(' ')
    for queue_name in queue_names:
        celery_queues[queue_name] = {
            'binding_key': queue_name,
            }
        check_circular_fallbacks(queue_name)

    parser = argparse.ArgumentParser()
    parser.add_argument('-Q',  '--queues')
    args = parser.parse_known_args(argv)
    queues = args[0].queues
    # A queue must be specified as a command line parameter for each
    # celeryd instance, but this is not required for a Launchpad app server.
    if 'celeryd' in argv[0]:
        if queues is None or queues == '':
            raise ConfigurationError('A queue must be specified.')
        queues = queues.split(',')
        # Allow only one queue per celeryd instance. More than one queue
        # would require a check for consistent timeout values, and especially
        # a better way to specify a fallback queue.
        if len(queues) > 1:
            raise ConfigurationError(
                'A celeryd instance may serve only one queue.')
        queue = queues[0]
        if queue not in celery_queues:
            raise ConfigurationError(
                'Queue %s is not configured in schema-lazr.conf' % queue)
        result['CELERYD_TASK_SOFT_TIME_LIMIT'] = config[queue].timeout
        if config[queue].fallback_queue != '':
            result['FALLBACK'] = config[queue].fallback_queue
        result['CELERYD_CONCURRENCY'] = config[queue].concurrency

    host, port = config.rabbitmq.host.split(':')

    result['BROKER_HOST'] = host
    result['BROKER_PORT'] = port
    result['BROKER_USER'] = config.rabbitmq.userid
    result['BROKER_PASSWORD'] = config.rabbitmq.password
    result['BROKER_VHOST'] = config.rabbitmq.virtual_host
    result['CELERY_CREATE_MISSING_QUEUES'] = False
    result['CELERY_DEFAULT_EXCHANGE'] = 'job'
    result['CELERY_DEFAULT_QUEUE'] = 'launchpad_job'
    result['CELERY_IMPORTS'] = ("lp.services.job.celeryjob", )
    result['CELERY_QUEUES'] = celery_queues
    result['CELERY_RESULT_BACKEND'] = 'amqp'
    result['CELERYBEAT_SCHEDULE'] = {
        'schedule-missing': {
            'task': 'lp.services.job.celeryjob.run_missing_ready',
            'schedule': timedelta(seconds=600),
            'options': {
                'routing_key': CELERY_BEAT_QUEUE,
                },
        }
    }
    # See http://ask.github.com/celery/userguide/optimizing.html:
    # The AMQP message of a job should stay in the RabbitMQ server
    # until the job has been finished. This allows to simply kill
    # a celeryd instance while a job is executed; when another
    # instance is started later, it will run the aborted job again.
    result['CELERYD_PREFETCH_MULTIPLIER'] = 1
    result['CELERY_ACKS_LATE'] = True

    return result

try:
    globals().update(configure(getattr(sys, 'argv', [''])))
except ConfigurationError as error:
    print >>sys.stderr, error
    sys.exit(1)
