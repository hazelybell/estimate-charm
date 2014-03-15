#!/usr/bin/python
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
This script runs a simple HTTP server. The server returns XML files
when given certain user-configurable URLs.
"""


from BaseHTTPServer import (
    BaseHTTPRequestHandler,
    HTTPServer,
    )
import errno
import logging
import os
import signal
import socket
import subprocess
import time

from lp.services.config import config
from lp.services.osutils import ensure_directory_exists
from lp.services.pidfile import (
    get_pid,
    make_pidfile,
    pidfile_path,
    )
from lp.services.webapp.url import urlsplit

# Set up basic logging.
log = logging.getLogger(__name__)

# The default service name, used by the Launchpad service framework.
service_name = 'google-webservice'


class GoogleRequestHandler(BaseHTTPRequestHandler):
    """Return an XML file depending on the requested URL."""

    default_content_type = 'text/xml; charset=UTF-8'

    def do_GET(self):
        """See BaseHTTPRequestHandler in the Python Standard Library."""
        urlmap = url_to_xml_map()
        if self.path in urlmap:
            self.return_file(urlmap[self.path])
        else:
            # Return our default route.
            self.return_file(urlmap['*'])

    def return_file(self, filename):
        """Return a HTTP response with 'filename' for content.

        :param filename: The file name to find in the canned-data
            storage location.
        """
        self.send_response(200)
        self.send_header('Content-Type', self.default_content_type)
        self.end_headers()

        content_dir = config.google_test_service.canned_response_directory
        filepath = os.path.join(content_dir, filename)
        content_body = file(filepath).read()
        self.wfile.write(content_body)

    def log_message(self, format, *args):
        """See `BaseHTTPRequestHandler.log_message()`."""
        # Substitute the base class's logger with the Python Standard
        # Library logger.
        message = ("%s - - [%s] %s" %
                   (self.address_string(),
                    self.log_date_time_string(),
                    format%args))
        log.info(message)


def url_to_xml_map():
    """Return our URL-to-XML mapping as a dictionary."""
    mapfile = config.google_test_service.mapfile
    mapping = {}
    for line in file(mapfile):
        if line.startswith('#') or len(line.strip()) == 0:
            # Skip comments and blank lines.
            continue
        url, fname = line.split()
        mapping[url.strip()] = fname.strip()

    return mapping


def get_service_endpoint():
    """Return the host and port that the service is running on."""
    return hostpair(config.google.site)


def service_is_available(timeout=2.0):
    """Return True if the service is up and running.

    :param timeout: BLOCK execution for at most 'timeout' seconds
        before returning False.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout) # Block for 'timeout' seconds.
    host, port = get_service_endpoint()
    try:
        try:
            sock.connect((host, port))
        except socket.error:
            return False
        else:
            return True
    finally:
        sock.close() # Clean up.


def wait_for_service(timeout=15.0):
    """Poll the service and BLOCK until we can connect to it.

    :param timeout: The socket should timeout after this many seconds.
        Refer to the socket module documentation in the Standard Library
        for possible timeout values.
    """
    host, port = get_service_endpoint()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout) # Block for at most X seconds.

    start = time.time()  # Record when we started polling.
    try:
        while True:
            try:
                sock.connect((host, port))
            except socket.error as err:
                if err.args[0] in [errno.ECONNREFUSED, errno.ECONNABORTED]:
                    elapsed = (time.time() - start)
                    if elapsed > timeout:
                        raise RuntimeError("Socket poll time exceeded.")
                else:
                    raise
            else:
                break
            time.sleep(0.1)
    finally:
        sock.close()  # Clean up.


def wait_for_service_shutdown(seconds_to_wait=10.0):
    """Poll the service until it shuts down.

    Raises a RuntimeError if the service doesn't shut down within the allotted
    time, under normal operation.  It may also raise various socket errors if
    there are issues connecting to the service (host lookup, etc.)

    :param seconds_to_wait: The number of seconds to wait for the socket to
        open up.
    """
    host, port = get_service_endpoint()

    start = time.time()  # Record when we started polling.
    try:
        while True:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0) # Block for at most X seconds.
            try:
                sock.connect((host, port))
                sock.close()
            except socket.error as err:
                if err.args[0] == errno.ECONNREFUSED:
                    # Success!  The socket is closed.
                    return
                else:
                    raise
            else:
                elapsed = (time.time() - start)
                if elapsed > seconds_to_wait:
                    raise RuntimeError(
                        "The service did not shut down in the allotted time.")
            time.sleep(0.1)
    finally:
        sock.close()  # Clean up.


def hostpair(url):
    """Parse the host and port number out of a URL string."""
    parts  = urlsplit(url)
    host, port = parts[1].split(':')
    port = int(port)
    return (host, port)


def start_as_process():
    """Run this file as a stand-alone Python script.

    Returns a subprocess.Popen object. (See the `subprocess` module in
    the Python Standard Library for details.)
    """
    script = os.path.join(
        os.path.dirname(__file__),
        os.pardir, os.pardir, os.pardir, os.pardir, 'bin',
        'googletestservice')
    # Make sure we aren't using the parent stdin and stdout to avoid spam
    # and have fewer things that can go wrong shutting down the process.
    proc = subprocess.Popen(
        script, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    proc.stdin.close()
    return proc


def kill_running_process():
    """Find and kill any running web service processes."""
    global service_name
    try:
        pid = get_pid(service_name)
    except IOError:
        # We could not find an existing pidfile.
        return
    except ValueError:
        # The file contained a mangled and invalid PID number, so we should
        # clean the file up.
        safe_unlink(pidfile_path(service_name))
    else:
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
                # We need to use a busy-wait to find out when the socket
                # becomes available.  Failing to do so causes a race condition
                # between freeing the socket in the killed process, and
                # opening it in the current one.
                wait_for_service_shutdown()
            except os.error as err:
                if err.errno == errno.ESRCH:
                    # Whoops, we got a 'No such process' error. The PID file
                    # is probably stale, so we'll remove it to prevent trash
                    # from lying around in the test environment.
                    # See bug #237086.
                    safe_unlink(pidfile_path(service_name))
                else:
                    raise


def safe_unlink(filepath):
    """Unlink a file, but don't raise an error if the file is missing."""
    try:
        os.unlink(filepath)
    except os.error as err:
        if err.errno != errno.ENOENT:
            raise


def main():
    """Run the HTTP server."""
    # Redirect our service output to a log file.
    global log
    ensure_directory_exists(os.path.dirname(config.google_test_service.log))
    filelog = logging.FileHandler(config.google_test_service.log)
    log.addHandler(filelog)
    log.setLevel(logging.DEBUG)

    # To support service shutdown we need to create a PID file that is
    # understood by the Launchpad services framework.
    global service_name
    make_pidfile(service_name)

    host, port = get_service_endpoint()
    server = HTTPServer((host, port), GoogleRequestHandler)

    log.info("Starting HTTP Google webservice server on port %s", port)
    server.serve_forever()
