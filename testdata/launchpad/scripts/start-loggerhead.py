#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

import logging
from optparse import OptionParser
import os
import sys
import time
import traceback

from paste import httpserver
from paste.deploy.config import PrefixMiddleware
from paste.httpexceptions import HTTPExceptionHandler
from paste.request import construct_url
from paste.translogger import TransLogger
from paste.wsgilib import catch_errors

import lp.codehosting
from lp.services.config import config


LISTEN_HOST = config.codebrowse.listen_host
LISTEN_PORT = config.codebrowse.port
THREADPOOL_WORKERS = 10


class NoLockingFileHandler(logging.FileHandler):
    """A version of logging.FileHandler that doesn't do it's own locking.

    We experienced occasional hangs in production where gdb-ery on the server
    revealed that we sometimes end up with many threads blocking on the RLock
    held by the logging file handler, and log reading finds that an exception
    managed to kill a thread in an unsafe window for RLock's.

    Luckily, there's no real reason for us to take a lock during logging as
    each log message translates to one call to .write on a file object, which
    translates to one fwrite call, and it seems that this does enough locking
    itself for our purposes.

    So this handler just doesn't lock in log message handling.
    """

    def acquire(self):
        pass

    def release(self):
        pass


def setup_logging(home, foreground):
    # i hate that stupid logging config format, so just set up logging here.

    log_folder = config.codebrowse.log_folder
    if not log_folder:
        log_folder = os.path.join(home, 'logs')
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    f = logging.Formatter(
        '%(levelname)-.3s [%(asctime)s.%(msecs)03d] [%(thread)d] %(name)s: %(message)s',
        '%Y%m%d-%H:%M:%S')
    debug_log = NoLockingFileHandler(os.path.join(log_folder, 'debug.log'))
    debug_log.setLevel(logging.DEBUG)
    debug_log.setFormatter(f)
    if foreground:
        stdout_log = logging.StreamHandler(sys.stdout)
        stdout_log.setLevel(logging.DEBUG)
        stdout_log.setFormatter(f)
    f = logging.Formatter('[%(asctime)s.%(msecs)03d] %(message)s',
                          '%Y%m%d-%H:%M:%S')
    access_log = NoLockingFileHandler(os.path.join(log_folder, 'access.log'))
    access_log.setLevel(logging.INFO)
    access_log.setFormatter(f)

    logging.getLogger('').setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(debug_log)
    logging.getLogger('wsgi').addHandler(access_log)

    if foreground:
        logging.getLogger('').addHandler(stdout_log)
    else:
        class S(object):
            def write(self, str):
                logging.getLogger().error(str.rstrip('\n'))
            def flush(self):
                pass
        sys.stderr = S()


parser = OptionParser(description="Start loggerhead.")
parser.add_option(
    "-f", "--foreground", default=False, action="store_true",
    help="Run loggerhead in the foreground.")
options, _ = parser.parse_args()

home = os.path.realpath(os.path.dirname(__file__))
pidfile = os.path.join(home, 'loggerhead.pid')

if not options.foreground:
    sys.stderr.write('\n')
    sys.stderr.write('Launching loggerhead into the background.\n')
    sys.stderr.write('PID file: %s\n' % (pidfile,))
    sys.stderr.write('\n')

    from loggerhead.daemon import daemonize
    daemonize(pidfile, home)

setup_logging(home, foreground=options.foreground)

log = logging.getLogger('loggerhead')
log.info('Starting up...')

log.info('Loading the bzr plugins...')
from bzrlib.plugin import load_plugins
load_plugins()

import bzrlib.plugins
if getattr(bzrlib.plugins, 'loom', None) is None:
    log.error('Loom plugin loading failed.')

from launchpad_loggerhead.debug import (
    change_kill_thread_criteria, threadpool_debug)
from launchpad_loggerhead.app import RootApp, oops_middleware
from launchpad_loggerhead.session import SessionHandler

SESSION_VAR = 'lh.session'

secret = open(os.path.join(config.root, config.codebrowse.secret_path)).read()

app = RootApp(SESSION_VAR)
app = HTTPExceptionHandler(app)
app = SessionHandler(app, SESSION_VAR, secret)
def log_request_start_and_stop(app):
    def wrapped(environ, start_response):
        log = logging.getLogger('loggerhead')
        url = construct_url(environ)
        log.info("Starting to process %s", url)
        start_time = time.time()
        def request_done_ok():
            log.info("Processed ok %s [%0.3f seconds]", url, time.time() -
                    start_time)
        def request_done_err(exc_info):
            log.info("Processed err %s [%0.3f seconds]: %s", url, time.time() -
                    start_time, traceback.format_exception_only(*exc_info[:2]))
        return catch_errors(app, environ, start_response, request_done_err,
                request_done_ok)
    return wrapped
app = log_request_start_and_stop(app)
app = PrefixMiddleware(app)
app = TransLogger(app)
app = threadpool_debug(app)

def set_scheme(app):
    """Set wsgi.url_scheme in the environment correctly.

    We serve requests that originated from both http and https, and
    distinguish between them by adding a header in the https Apache config.
    """
    def wrapped(environ, start_response):
        environ['wsgi.url_scheme'] = environ.pop(
            'HTTP_X_FORWARDED_SCHEME', 'http')
        return app(environ, start_response)
    return wrapped
app = set_scheme(app)
app = change_kill_thread_criteria(app)
app = oops_middleware(app)

try:
    httpserver.serve(
        app, host=LISTEN_HOST, port=LISTEN_PORT,
        threadpool_workers=THREADPOOL_WORKERS,
        threadpool_options={
            # Kill threads after 300 seconds.  This is insanely high, but
            # lower enough than the default (1800 seconds!) that evidence
            # suggests it will be hit occasionally, and there's very little
            # chance of it having negative consequences.
            'kill_thread_limit': 300,
            # Check for threads that should be killed every 10 requests.  The
            # default is every 100, which is easily long enough for things to
            # gum up completely in between checks.
            'hung_check_period': 10,
            })
finally:
    log.info('Shutdown.')
    try:
        os.remove(pidfile)
    except OSError:
        pass
