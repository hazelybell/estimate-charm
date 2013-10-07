# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from lp.soyuz.adapters.buildarch import determine_architectures_to_build
from lp.soyuz.tests.test_publishing import SoyuzTestPublisher
from lp.testing import TestCaseWithFactory
from lp.testing.layers import LaunchpadZopelessLayer


class TestDetermineArchitecturesToBuild(TestCaseWithFactory):
    """Test that determine_architectures_to_build correctly interprets hints.
    """

    layer = LaunchpadZopelessLayer

    def setUp(self):
        super(TestDetermineArchitecturesToBuild, self).setUp()
        self.publisher = SoyuzTestPublisher()
        self.publisher.prepareBreezyAutotest()
        armel = self.factory.makeProcessor('armel', 'armel', 'armel')
        self.publisher.breezy_autotest.newArch(
            'armel', armel, False, self.publisher.person)
        self.publisher.addFakeChroots()

    def assertArchitecturesToBuild(self, expected_arch_tags, pub,
                                   allowed_arch_tags=None):
        if allowed_arch_tags is None:
            allowed_archs = self.publisher.breezy_autotest.architectures
        else:
            allowed_archs = [
                arch for arch in self.publisher.breezy_autotest.architectures
                if arch.architecturetag in allowed_arch_tags]
        architectures = determine_architectures_to_build(
            pub.sourcepackagerelease.architecturehintlist, pub.archive,
            self.publisher.breezy_autotest, allowed_archs)
        self.assertContentEqual(
            expected_arch_tags, [a.architecturetag for a in architectures])

    def assertArchsForHint(self, hint_string, expected_arch_tags,
                           allowed_arch_tags=None, sourcename=None):
        """Assert that the given hint resolves to the expected archtags."""
        pub = self.publisher.getPubSource(
            sourcename=sourcename, architecturehintlist=hint_string)
        self.assertArchitecturesToBuild(
            expected_arch_tags, pub, allowed_arch_tags=allowed_arch_tags)

    def test_single_architecture(self):
        # A hint string with a single arch resolves to just that arch.
        self.assertArchsForHint('hppa', ['hppa'])

    def test_three_architectures(self):
        # A hint string with multiple archs resolves to just those
        # archs.
        self.assertArchsForHint('amd64 i386 hppa', ['hppa', 'i386'])

    def test_independent(self):
        # 'all' is special, meaning just a single build. The
        # nominatedarchindep architecture is used -- in this case i386.
        self.assertArchsForHint('all', ['i386'])

    def test_one_and_independent(self):
        # 'all' is redundant if we have another build anyway.
        self.assertArchsForHint('hppa all', ['hppa'])

    def test_fictional_and_independent(self):
        # But 'all' is useful if present with an arch that wouldn't
        # generate a build.
        self.assertArchsForHint('foo all', ['i386'])

    def test_wildcard(self):
        # 'any' is a wildcard that matches all available archs.
        self.assertArchsForHint('any', ['armel', 'hppa', 'i386'])

    def test_kernel_specific_architecture(self):
        # Since we only support Linux-based architectures, 'linux-foo'
        # is treated the same as 'foo'.
        self.assertArchsForHint('linux-hppa', ['hppa'])

    def test_unknown_kernel_specific_architecture(self):
        # Non-Linux architectures aren't supported.
        self.assertArchsForHint('kfreebsd-hppa', [])

    def test_kernel_wildcard_architecture(self):
        # Wildcards work for kernels: 'any-foo' is treated like 'foo'.
        self.assertArchsForHint('any-hppa', ['hppa'])

    def test_kernel_wildcard_architecture_arm(self):
        # The second part of a wildcard matches the canonical CPU name, not
        # on the Debian architecture, so 'any-arm' matches 'armel'.
        self.assertArchsForHint('any-arm', ['armel'])

    def test_kernel_specific_architecture_wildcard(self):
        # Wildcards work for archs too: 'linux-any' is treated like 'any'.
        self.assertArchsForHint('linux-any', ['armel', 'hppa', 'i386'])

    def test_unknown_kernel_specific_architecture_wildcard(self):
        # But unknown kernels continue to result in nothing.
        self.assertArchsForHint('kfreebsd-any', [])

    def test_wildcard_and_independent(self):
        # 'all' continues to be ignored alongside a valid wildcard.
        self.assertArchsForHint('all linux-any', ['armel', 'hppa', 'i386'])

    def test_kernel_independent_is_invalid(self):
        # 'linux-all' isn't supported.
        self.assertArchsForHint('linux-all', [])

    def test_double_wildcard_is_same_as_single(self):
        # 'any-any' is redundant with 'any', but dpkg-architecture supports
        # it anyway.
        self.assertArchsForHint('any-any', ['armel', 'hppa', 'i386'])

    def test_disabled_architectures_omitted(self):
        # Disabled architectures are not buildable, so are excluded.
        self.publisher.breezy_autotest['hppa'].enabled = False
        self.assertArchsForHint('any', ['armel', 'i386'])

    def test_virtualized_archives_have_only_virtualized_archs(self):
        # For archives which must build on virtual builders, only
        # virtual archs are returned.
        self.publisher.breezy_autotest.main_archive.require_virtualized = True
        self.assertArchsForHint('any', ['i386'])

    def test_no_all_builds_when_nominatedarchindep_not_permitted(self):
        # Some archives (eg. armel rebuilds) don't want arch-indep
        # builds. If the nominatedarchindep architecture (normally
        # i386) is omitted, no builds will be created for arch-indep
        # sources.
        self.assertArchsForHint('all', [], allowed_arch_tags=['hppa'])
