# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for choosing the preferred charsets."""

__metaclass__ = type

from lp.testing.systemdocs import LayeredDocFileSuite


def test_suite():
    return LayeredDocFileSuite(
        'test_preferredcharsets.txt')

