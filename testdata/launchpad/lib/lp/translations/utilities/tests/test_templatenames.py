# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import unittest

from lp.translations.utilities.template import (
    make_domain,
    make_name,
    make_name_from_path,
    )


class TemplateNamesTest(unittest.TestCase):
    """Test template name conversion utility function."""

    meaningful_path_domain = 'my_domain'
    meaningful_paths = [
        "my_domain.pot",
        "po/my_domain.pot",
        "my_domain/messages.pot",
        "po/my_domain/messages.pot",
        "my_domain/po/messages.pot",
        "my_domain/en-US.xpi",
        ]

    meaningless_paths = [
        "messages.pot",
        "po/messages.pot",
        "en-US.xpi",
        "po/en-US.xpi",
        ]

    def test_make_domain_extracts_domain_from_meaningful_paths(self):
        # make_domain will spot a meaningful identifier in a typical
        # useful template file path.
        for path in self.meaningful_paths:
            domain = make_domain(path)
            self.assertEqual(
                self.meaningful_path_domain, domain,
                "Path '%s' yielded domain '%s'; should have found '%s'."
                % (path, domain, self.meaningful_path_domain))

    def test_make_domain_finds_no_domain_in_meaningless_paths(self):
        # make_domain will not find any usable identifiers in a typical
        # meaningless template file path, and default to the empty
        # string.
        for path in self.meaningless_paths:
            domain = make_domain(path)
            self.assertEqual(
                '', domain,
                "Path '%s' yielded domain '%s'; should have found nothing."
                % (path, domain))

    def test_make_domain_falls_back_on_default(self):
        # When a path contains no usable identifier, make_domain falls
        # back on the default you pass it.
        default_domain = 'default_fallback'
        for path in self.meaningless_paths:
            domain = make_domain(path, default=default_domain)
            self.assertEqual(
                default_domain, domain,
                "Path '%s' yielded domain '%s'; expected default '%s'."
                % (path, domain, default_domain))

    def test_make_name_underscore(self):
        # Underscores are converted to dashes for template names.
        self.assertEqual('my-domain', make_name('my_domain'))

    def test_make_name_lowercase(self):
        # Upper case letters are converted to lower case for template names.
        self.assertEqual('mydomain', make_name('MyDomain'))

    def test_make_name_invalid_chars(self):
        # Invalid characters are removed for template names.
        self.assertEqual('my-domain', make_name('my - do@ #*$&main'))

    def test_make_name_from_path(self):
        # Chain both methods for convenience.
        self.assertEqual(
            'my-domain', make_name_from_path("po/My_Do@main/messages.pot"))

    def test_make_name_from_path_falls_back_on_default(self):
        # make_name_from_path falls back on the default you pass if the
        # path contains no helpful identifiers.
        default_name = 'default-name'
        self.assertEqual(
            default_name,
            make_name_from_path('messages.pot', default=default_name))

    def test_make_name_from_path_sanitizes_default(self):
        # If make_name_from_path has to fall back on the default you
        # pass, it sanitizes the domain it gets for use as a template
        # name, just as it would a domain that was extracted from the
        # path.
        self.assertEqual(
            "foo-bar",
            make_name_from_path('messages.pot', default="foo_bar"))
