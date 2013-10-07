# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the doctestcodec module."""

__metaclass__ = type
__all__ = []

from doctest import DocTestSuite

import lp.services.testing.doctestcodec


def test_suite():
    return DocTestSuite(lp.services.testing.doctestcodec)
