# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A SIGUSR1 handler for the Launchpad Web App.

To aid debugging, we install a handler for the SIGUSR1 signal.  When
received, a summary of the last request, recent OOPS IDs and last
executed SQL statement is printed for each thread.
"""

import logging
import signal
import threading


def sigusr1_handler(signum, frame):
    """Log status of running threads in response to SIGUSR1"""
    message = ['Thread summary:']
    for thread in threading.enumerate():
        # if the thread has no lp_last_request attribute, it probably
        # isn't an appserver thread.
        if not hasattr(thread, 'lp_last_request'):
            continue
        message.append('\t%s' % thread.getName())
        message.append('\t\tLast Request: %s' % thread.lp_last_request)
        message.append('\t\tMost recent OOPS IDs: %s' %
                       ', '.join(getattr(thread, 'lp_last_oops', [])))
        message.append('\t\tLast SQL statement: %s' %
                       getattr(thread, 'lp_last_sql_statement', None))
    logging.getLogger('sigusr1').info('\n'.join(message))

def setup_sigusr1(event):
    """Configure the SIGUSR1 handler.  Called at startup."""
    signal.signal(signal.SIGUSR1, sigusr1_handler)

def before_traverse(event):
    """Record the request URL (provided that the request has a URL)"""
    request = event.request
    threading.currentThread().lp_last_request = str(
        getattr(request, 'URL', ''))

def end_request(event):
    """Record the OOPS ID in the thread, if one occurred."""
    request = event.request
    if request.oopsid is not None:
        thread = threading.currentThread()
        last_oops_ids = getattr(thread, 'lp_last_oops', [])
        # make sure the OOPS ID list has at most 5 elements
        thread.lp_last_oops = last_oops_ids[-4:] + [request.oopsid]
