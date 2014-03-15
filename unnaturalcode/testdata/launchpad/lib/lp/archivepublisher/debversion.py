# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Parse and compare Debian version strings.

This module contains a class designed to sit in your Python code pretty
naturally and represent a Debian version string.  It implements various
special methods to make dealing with them sweet.
"""

__metaclass__ = type

# This code came from sourcerer but has been heavily modified since.

import re

from debian import changelog

# Regular expressions make validating things easy
valid_epoch = re.compile(r'^[0-9]+$')
valid_upstream = re.compile(r'^[0-9][A-Za-z0-9+:.~-]*$')
valid_revision = re.compile(r'^[A-Za-z0-9+.~]+$')

VersionError = changelog.VersionError


class BadInputError(VersionError):
    pass


class BadEpochError(BadInputError):
    pass


class BadUpstreamError(BadInputError):
    pass


class BadRevisionError(BadInputError):
    pass


class Version(changelog.Version):
    """Debian version number.

    This class is designed to be reasonably transparent and allow you
    to write code like:

    |   s.version >= '1.100-1'

    The comparison will be done according to Debian rules, so '1.2' will
    compare lower.

    Properties:
      epoch       Epoch
      upstream    Upstream version
      debian_version    Debian/local revision
    """

    def __init__(self, ver):

        ver = str(ver)
        if not len(ver):
            raise BadInputError("Input cannot be empty")

        try:
            changelog.Version.__init__(self, ver)
        except ValueError as e:
            raise VersionError(e)

        if self.epoch is not None:
            if not len(self.epoch):
                raise BadEpochError("Epoch cannot be empty")
            if not valid_epoch.match(self.epoch):
                raise BadEpochError("Bad epoch format")

        if self.debian_version is not None:
            if self.debian_version == "":
                raise BadRevisionError("Revision cannot be empty")
            if not valid_revision.search(self.debian_version):
                raise BadRevisionError("Bad revision format")

        if not len(self.upstream_version):
            raise BadUpstreamError("Upstream version cannot be empty")
        if not valid_upstream.search(self.upstream_version):
            raise BadUpstreamError(
                "Bad upstream version format %s" % self.upstream_version)
