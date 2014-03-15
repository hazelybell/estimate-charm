# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Useful tools for interacting with Twisted."""

__metaclass__ = type
__all__ = [
    'cancel_on_timeout',
    'defer_to_thread',
    'extract_result',
    'gatherResults',
    'no_traceback_failures',
    'suppress_stderr',
    'run_reactor',
    ]


import functools
from signal import (
    getsignal,
    SIGCHLD,
    signal,
    )
import StringIO
import sys

from twisted.internet import (
    defer,
    reactor as default_reactor,
    threads,
    )
from twisted.python.failure import Failure


def defer_to_thread(function):
    """Run in a thread and return a Deferred that fires when done."""

    @functools.wraps(function)
    def decorated(*args, **kwargs):
        return threads.deferToThread(function, *args, **kwargs)

    return decorated


def gatherResults(deferredList):
    """Returns list with result of given Deferreds.

    This differs from Twisted's `defer.gatherResults` in two ways.

     1. It fires the actual first error that occurs, rather than wrapping
        it in a `defer.FirstError`.
     2. All errors apart from the first are consumed. (i.e. `consumeErrors`
        is True.)

    :type deferredList:  list of `defer.Deferred`s.
    :return: `defer.Deferred`.
    """
    def convert_first_error_to_real(failure):
        failure.trap(defer.FirstError)
        return failure.value.subFailure

    d = defer.DeferredList(deferredList, fireOnOneErrback=1, consumeErrors=1)
    d.addCallback(defer._parseDListResult)
    d.addErrback(convert_first_error_to_real)
    return d


def suppress_stderr(function):
    """Deferred friendly decorator that suppresses output from a function.
    """
    def set_stderr(result, stream):
        sys.stderr = stream
        return result

    @functools.wraps(function)
    def wrapper(*arguments, **keyword_arguments):
        saved_stderr = sys.stderr
        ignored_stream = StringIO.StringIO()
        sys.stderr = ignored_stream
        d = defer.maybeDeferred(function, *arguments, **keyword_arguments)
        return d.addBoth(set_stderr, saved_stderr)

    return wrapper


def extract_result(deferred):
    """Extract the result from a fired deferred.

    It can happen that you have an API that returns Deferreds for
    compatibility with Twisted code, but is in fact synchronous, i.e. the
    Deferreds it returns have always fired by the time it returns.  In this
    case, you can use this function to convert the result back into the usual
    form for a synchronous API, i.e. the result itself or a raised exception.

    It would be very bad form to use this as some way of checking if a
    Deferred has fired.
    """
    failures = []
    successes = []
    deferred.addCallbacks(successes.append, failures.append)
    if len(failures) == 1:
        failures[0].raiseException()
    elif len(successes) == 1:
        return successes[0]
    else:
        raise AssertionError("%r has not fired yet." % (deferred,))


def cancel_on_timeout(d, timeout, reactor=None):
    """Cancel a Deferred if it doesn't fire before the timeout is up.

    :param d: The Deferred to cancel
    :param timeout: The timeout in seconds
    :param reactor: Override the default reactor (useful for tests).

    :return: The same deferred, d.
    """
    if reactor is None:
        reactor = default_reactor
    delayed_call = reactor.callLater(timeout, d.cancel)

    def cancel_timeout(passthrough):
        if not delayed_call.called:
            delayed_call.cancel()
        return passthrough
    return d.addBoth(cancel_timeout)


def no_traceback_failures(func):
    """Decorator to return traceback-less Failures instead of raising errors.

    This is useful for functions used as callbacks or errbacks for a Deferred.
    Traceback-less failures are much faster than the automatic Failures
    Deferred constructs internally.
    """
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaseException as e:
            return Failure(e)

    return wrapped


def run_reactor():
    """Run the reactor and return with the SIGCHLD handler unchanged."""
    handler = getsignal(SIGCHLD)
    try:
        default_reactor.run()
    finally:
        signal(SIGCHLD, handler)
