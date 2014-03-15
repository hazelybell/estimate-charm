# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Copy `DistroSeries` translations from its parent series."""

__metaclass__ = type
__all__ = ['copy_distroseries_translations']


from zope.component import getUtility

from lp.registry.interfaces.distroseries import IDistroSeriesSet


class SeriesTranslationFlagsModified(Warning):
    """`DistroSeries`' translation flags were modified while we were working.

    The flags `DistroSeries.hide_all_translations` and
    `DistroSeries.defer_translation_imports` flags were set before
    `update_translations` started updating the `DistroSeries`' translations,
    but someone else modified their state before it completed.
    """


class SeriesStateKeeper:
    """Prepare `DistroSeries` state for copying, and later restore it.

    This class is built to act across transaction boundaries, so it can't
    store references to database objects.
    """

    series_id = None
    hide_all_translations = None
    defer_translation_imports = None

    def prepare(self, series):
        """Set up `series`' state for a translations update.

        Use `restore` later to bring `series` back to its original state.
        """
        self.series_id = series.id
        self.hide_all_translations = series.hide_all_translations
        self.defer_translation_imports = series.defer_translation_imports
        series.hide_all_translations = True
        series.defer_translation_imports = True

    def restore(self):
        """Restore `series` to its normal state after translations update."""
        # Re-read series from database.  We can't keep a reference to the
        # database object, since transactions may have been committed since
        # prepare() was called.
        series = getUtility(IDistroSeriesSet).get(self.series_id)

        flags_modified = (
            not series.hide_all_translations or
            not series.defer_translation_imports)

        if flags_modified:
            # The flags have been changed while we were working.  Play safe
            # and don't touch them.
            raise SeriesTranslationFlagsModified(
                "Translations flags for %s have been changed while copy was "
                "in progress. "
                "Please check the hide_all_translations and "
                "defer_translation_imports flags for %s, since they may "
                "affect users' ability to work on this series' translations."
                    % (series.name, series.name))

        # Restore flags.
        series.hide_all_translations = self.hide_all_translations
        series.defer_translation_imports = self.defer_translation_imports


def copy_distroseries_translations(distroseries, txn, logger):
    """Copy `distroseries` translations from its parents.

    Wraps around `DistroSeries.copyMissingTranslationsFromParent`, but also
    ensures that the `hide_all_translations` and `defer_translation_imports`
    flags are set.  After copying they are restored to their previous state.
    """
    statekeeper = SeriesStateKeeper()
    statekeeper.prepare(distroseries)
    name = distroseries.name
    txn.commit()
    txn.begin()

    copy_failed = False

    try:
        # Do the actual work.
        distroseries.copyTranslationsFromParent(txn, logger)
    except:
        copy_failed = True
        # Give us a fresh transaction for proper cleanup.
        txn.abort()
        txn.begin()
        raise
    finally:
        try:
            statekeeper.restore()
        except Warning as message:
            logger.warning(message)
        except:
            logger.warning(
                "Failed to restore hide_all_translations and "
                "defer_translation_imports flags on %s after translations "
                "copy failed.  Please check them manually." % name)
            # If the original copying etc. in the main try block failed, that
            # is the error most worth propagating.  Propagate a failure in
            # restoring the translations flags only if everything else went
            # well.
            if not copy_failed:
                raise
