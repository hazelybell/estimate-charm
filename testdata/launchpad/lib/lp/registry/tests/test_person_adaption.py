# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for person.py."""

__all__ = [
    'test_suite',
    ]

from lp.testing.systemdocs import LayeredDocFileSuite


def test_suite():
    return LayeredDocFileSuite('person_from_principal.txt')

