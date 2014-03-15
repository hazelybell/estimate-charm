# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import thread
import time

from paste.request import construct_url


def tabulate(cells):
    """Format a list of lists of strings in a table.

    The 'cells' are centered.

    >>> print ''.join(tabulate(
    ...     [['title 1', 'title 2'],
    ...      ['short', 'rather longer']]))
     title 1     title 2
      short   rather longer
    """
    widths = {}
    for row in cells:
        for col_index, cell in enumerate(row):
            widths[col_index] = max(len(cell), widths.get(col_index, 0))
    result = []
    for row in cells:
        result_row = ''
        for col_index, cell in enumerate(row):
            result_row += cell.center(widths[col_index] + 2)
        result.append(result_row.rstrip() + '\n')
    return result


def threadpool_debug(app):
    """Wrap `app` to provide debugging information about the threadpool state.

    The returned application will serve debugging information about the state
    of the threadpool at '/thread-debug' -- but only when accessed directly,
    not when accessed through Apache.
    """
    def wrapped(environ, start_response):
        if ('HTTP_X_FORWARDED_SERVER' in environ
            or environ['PATH_INFO'] != '/thread-debug'):
            environ['lp.timestarted'] = time.time()
            return app(environ, start_response)
        threadpool = environ['paste.httpserver.thread_pool']
        start_response("200 Ok", [])
        output = [("url", "time running", "time since last activity")]
        now = time.time()
        # Because we're accessing mutable structures without locks here,
        # we're a bit cautious about things looking like we expect -- if a
        # worker doesn't seem fully set up, we just ignore it.
        for worker in threadpool.workers:
            if not hasattr(worker, 'thread_id'):
                continue
            time_started, info = threadpool.worker_tracker.get(
                worker.thread_id, (None, None))
            if time_started is not None and info is not None:
                real_time_started = info.get(
                    'lp.timestarted', time_started)
                output.append(
                    map(str,
                        (construct_url(info),
                         now - real_time_started,
                         now - time_started,)))
        return tabulate(output)
    return wrapped


def change_kill_thread_criteria(application):
    """Interfere with threadpool so that threads are killed for inactivity.

    The usual rules with paste's threadpool is that a thread that takes longer
    than 'hung_thread_limit' seconds to process a request is considered hung
    and more than 'kill_thread_limit' seconds is killed.

    Because loggerhead streams its output, how long the entire request takes
    to process depends on things like how fast the users internet connection
    is.  What we'd like to do is kill threads that don't _start_ to produce
    output for 'kill_thread_limit' seconds.

    What this class actually does is arrange things so that threads that
    produce no output for 'kill_thread_limit' are killed, because that's the
    rule Apache uses when interpreting ProxyTimeout.
    """
    def wrapped_application(environ, start_response):
        threadpool = environ['paste.httpserver.thread_pool']
        def reset_timer():
            """Make this thread safe for another 'kill_thread_limit' seconds.

            We do this by hacking the threadpool's record of when this thread
            started to pretend that it started right now.  Hacky, but it's
            enough to fool paste.httpserver.ThreadPool.kill_hung_threads and
            that's what matters.
            """
            threadpool.worker_tracker[thread.get_ident()][0] = time.time()
        def response_hook(status, response_headers, exc_info=None):
            # We reset the timer when the HTTP headers are sent...
            reset_timer()
            writer = start_response(status, response_headers, exc_info)
            def wrapped_writer(arg):
                # ... and whenever more output has been generated.
                reset_timer()
                return writer(arg)
            return wrapped_writer
        result = application(environ, response_hook)
        # WSGI allows the application to return an iterable, which could be a
        # generator that does significant processing between successive items,
        # so we should reset the timer between each item.
        #
        # This isn't really necessary as loggerhead doesn't return any
        # non-trivial iterables to the WSGI server.  But it's probably better
        # to cope with this case to avoid nasty suprises if loggerhead
        # changes.
        def reset_timer_between_items(iterable):
            for item in iterable:
                reset_timer()
                yield item
        return reset_timer_between_items(result)
    return wrapped_application
