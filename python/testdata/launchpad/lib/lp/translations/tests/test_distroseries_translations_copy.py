# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Unit tests for distroseries translations initialization."""

__metaclass__ = type

from lp.services.database.multitablecopy import MultiTableCopy
from lp.services.log.logger import DevNullLogger
from lp.testing import TestCaseWithFactory
from lp.testing.faketransaction import FakeTransaction
from lp.testing.layers import ZopelessDatabaseLayer
from lp.translations.model.distroseries_translations_copy import (
    copy_active_translations,
    )


class EarlyExit(Exception):
    """Exception used to force early exit from the copying code."""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def force_exit(*args, **kwargs):
    """Raise `EarlyExit`."""
    raise EarlyExit(*args, **kwargs)


class TestDistroSeriesTranslationsCopying(TestCaseWithFactory):

    layer = ZopelessDatabaseLayer

    def test_does_not_overwrite_existing_pofile(self):
        # Sometimes a POFile we're about to copy to a new distroseries
        # has already been created there due to message sharing.  In
        # that case, the copying code leaves the existing POFile in
        # place and does not copy it.  (Nor does it raise an error.)
        existing_series = self.factory.makeDistroSeries(name='existing')
        new_series = self.factory.makeDistroSeries(
            name='new', distribution=existing_series.distribution,
            previous_series=existing_series)
        template = self.factory.makePOTemplate(distroseries=existing_series)
        pofile = self.factory.makePOFile(potemplate=template)
        self.factory.makeCurrentTranslationMessage(
            language=pofile.language, potmsgset=self.factory.makePOTMsgSet(
                potemplate=template))

        # Sabotage the pouring code so that when it's about to hit the
        # POFile table, it returns to us and we can simulate a race
        # condition.
        pour_table = MultiTableCopy._pourTable

        def pour_or_stop_at_pofile(self, holding_table, table, *args,
                                   **kwargs):
            args = (self, holding_table, table) + args
            if table.lower() == "pofile":
                raise EarlyExit(*args, **kwargs)
            else:
                return pour_table(*args, **kwargs)

        MultiTableCopy._pourTable = pour_or_stop_at_pofile
        try:
            copy_active_translations(
                new_series, FakeTransaction(), DevNullLogger())
        except EarlyExit as e:
            pour_args = e.args
            pour_kwargs = e.kwargs
        finally:
            MultiTableCopy._pourTable = pour_table

        # Simulate another POFile being created for new_series while the
        # copier was working.
        new_template = new_series.getTranslationTemplateByName(template.name)
        new_pofile = self.factory.makePOFile(
            potemplate=new_template, language=pofile.language)

        # Now continue pouring the POFile table.
        pour_table(*pour_args, **pour_kwargs)

        # The POFile we just created in our race condition stays in
        # place.  There is no error.
        resulting_pofile = new_template.getPOFileByLang(pofile.language.code)
        self.assertEqual(new_pofile, resulting_pofile)
