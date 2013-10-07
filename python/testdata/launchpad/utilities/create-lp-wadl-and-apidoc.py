#! /usr/bin/python -S
#
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Create a static WADL file describing the current webservice.

Example:

    % LPCONFIG=development bin/py utilities/create-lp-wadl-and-apidoc.py \\
      "lib/canonical/launchpad/apidoc/wadl-development-%(version)s.xml"
"""
import _pythonpath

from multiprocessing import Process
import optparse
import os
import sys

import bzrlib
from bzrlib.branch import Branch
from lazr.restful.interfaces import IWebServiceConfiguration
from z3c.ptcompat import PageTemplateFile
from zope.component import getUtility

from lp.services.scripts import execute_zcml_for_scripts
from lp.services.webservice.wadl import (
    generate_html,
    generate_json,
    generate_wadl,
    )
from lp.systemhomes import WebServiceApplication


def write(filename, content, timestamp):
    """Replace the named file with the given string."""
    f = open(filename, 'w')
    f.write(content)
    f.close()
    os.utime(filename, (timestamp, timestamp))  # (atime, mtime)


def make_files(directory, version, timestamp, force):
    version_directory = os.path.join(directory, version)
    base_filename = os.path.join(version_directory, os.environ['LPCONFIG'])
    wadl_filename = base_filename + '.wadl'
    json_filename = base_filename + '.json'
    html_filename = os.path.join(directory, version + ".html")
    wadl_index = os.path.join(version_directory, 'index.wadl')
    json_index = os.path.join(version_directory, 'index.json')
    html_index = os.path.join(version_directory, 'index.html')
    brokenwadl_index = os.path.join(version_directory, 'index.brokenwadl')

    # Make sure we have our dir.
    if not os.path.exists(version_directory):
        # We expect the main directory to exist.
        os.mkdir(version_directory)

    # Make wadl and json files.
    for src, dest, gen, name in (
        (wadl_filename, wadl_index, generate_wadl, 'WADL'),
        (json_filename, json_index, generate_json, 'JSON')):
        # If the src doesn't exist or we are forced to regenerate it...
        if (not os.path.exists(src) or force):
            print "Writing %s for version %s to %s." % (
                name, version, src)
            write(src, gen(version), timestamp)
        else:
            print "Skipping already present %s file: %s" % (
                name, src)
        # Make "index" symlinks, removing any preexisting ones.
        if os.path.exists(dest):
            os.remove(dest)
        os.symlink(os.path.basename(src), dest)

    # Make the brokenwadl symlink.  This is because we need to support a
    # misspelled wadl mimetype that some legacy launchpadlib versions used.
    # Multiple attempts have been made to make this unnecessary, and removing
    # it is welcome.  In particular, these two approaches were attempted in
    # Apache.
    #
    # Approach 1 (a variant of example 4
    # from http://httpd.apache.org/docs/2.0/mod/mod_headers.html)
    # SetEnvIf Accept \Qapplication/vd.sun.wadl+xml\E X_WADL_MIME
    # RequestHeader set Accept "application/vnd.sun.wadl+xml" env=X_WADL_MIME
    # This, at least in combination with Apache's MultiViews, doesn't work
    # in developer tests.
    #
    # Approach 2:
    # In mime.conf,
    # AddType application/vnd.sun.wadl+xml .wadl
    # AddType application/vd.sun.wadl+xml .wadl
    # In developer tests, it seems Apache only allows a single mime type
    # for a given extension.
    #
    # Therefore, the approach we use is
    # AddType application/vnd.sun.wadl+xml .wadl
    # AddType application/vd.sun.wadl+xml .brokenwadl
    # We support that here.
    if not os.path.exists(brokenwadl_index):
        os.symlink(os.path.basename(wadl_index), brokenwadl_index)

    # Now, convert the WADL into an human-readable description and
    # put the HTML in the same directory as the WADL.
    # If the HTML file doesn't exist or we're being forced to regenerate
    # it...
    if (not os.path.exists(html_filename) or force):
        print "Writing apidoc for version %s to %s" % (
            version, html_filename)
        write(html_filename, generate_html(wadl_filename,
            suppress_stderr=False), timestamp)
    else:
        print "Skipping already present HTML file:", html_filename

    # Symlink the top-level version html in the version directory for
    # completeness.
    if not os.path.exists(html_index):
        os.symlink(
            os.path.join(os.path.pardir, os.path.basename(html_filename)),
            html_index)


def main(directory, force=False):
    WebServiceApplication.cached_wadl = None  # do not use cached file version
    execute_zcml_for_scripts()
    config = getUtility(IWebServiceConfiguration)

    # First, create an index.html with links to all the HTML
    # documentation files we're about to generate.
    template_file = 'apidoc-index.pt'
    template = PageTemplateFile(template_file)
    index_filename = os.path.join(directory, "index.html")
    print "Writing index:", index_filename
    f = open(index_filename, 'w')
    f.write(template(config=config))

    # Get the time of the last commit.  We will use this as the mtime for the
    # generated files so that we can safely use it as part of Apache's etag
    # generation in the face of multiple servers/filesystems.
    with bzrlib.initialize():
        branch = Branch.open(os.path.dirname(os.path.dirname(__file__)))
        timestamp = branch.repository.get_revision(
            branch.last_revision()).timestamp

    # Start a process to build each set of WADL and HTML files.
    processes = []
    for version in config.active_versions:
        p = Process(target=make_files,
            args=(directory, version, timestamp, force))
        p.start()
        processes.append(p)

    # Wait for all the subprocesses to finish.
    for p in processes:
        p.join()

    return 0


def parse_args(args):
    usage = "usage: %prog [options] DIR"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option(
        "--force", action="store_true",
        help="Replace any already-existing files.")
    parser.set_defaults(force=False)
    options, args = parser.parse_args(args)
    if len(args) != 2:
        parser.error("A directory is required.")

    return options, args


if __name__ == '__main__':
    options, args = parse_args(sys.argv)
    sys.exit(main(args[1], options.force))
