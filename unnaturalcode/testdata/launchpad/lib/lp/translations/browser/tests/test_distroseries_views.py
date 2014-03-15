# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the translations views on a distroseries."""

__metaclass__ = type


from lp.testing import (
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import LaunchpadFunctionalLayer
from lp.testing.views import create_initialized_view
from lp.translations.enums import LanguagePackType


class TestLanguagePacksView(TestCaseWithFactory):
    """Test language packs view."""

    layer = LaunchpadFunctionalLayer

    def test_unused_language_packs_many_language_packs(self):
        distroseries = self.factory.makeUbuntuDistroSeries()
        # This is one more than the default for shortlist.
        number_of_language_packs = 16
        for i in range(number_of_language_packs):
            self.factory.makeLanguagePack(distroseries)

        view = create_initialized_view(
            distroseries, '+language-packs', rootsite='translations')
        # This should not trigger a shortlist warning.
        self.assertEqual(
            number_of_language_packs, len(view.unused_language_packs))

    def test_unused_language_packs_identical_base_proposed_pack(self):
        distroseries = self.factory.makeUbuntuDistroSeries()
        pack = self.factory.makeLanguagePack(distroseries)
        with person_logged_in(distroseries.distribution.owner):
            distroseries.language_pack_base = pack
            distroseries.language_pack_proposed = pack

        view = create_initialized_view(
            distroseries, '+language-packs', rootsite='translations')
        self.assertEqual(0, len(view.unused_language_packs))

    def test_unused_language_packs_identical_delta_proposed_pack(self):
        distroseries = self.factory.makeUbuntuDistroSeries()
        with person_logged_in(distroseries.distribution.owner):
            distroseries.language_pack_base = self.factory.makeLanguagePack(
                distroseries)
            delta_pack = self.factory.makeLanguagePack(
                distroseries, LanguagePackType.DELTA)
            distroseries.language_pack_delta = delta_pack
            distroseries.language_pack_proposed = delta_pack

        view = create_initialized_view(
            distroseries, '+language-packs', rootsite='translations')
        self.assertEqual(0, len(view.unused_language_packs))
