# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions to copy translations from previous to child distroseries."""

__metaclass__ = type

__all__ = [
    'copy_active_translations',
    ]

from lp.services.database.multitablecopy import MultiTableCopy
from lp.services.database.sqlbase import (
    cursor,
    quote,
    )


def omit_redundant_pofiles(from_table, to_table, batch_size, begin_id,
                           end_id):
    """Batch-pouring callback: skip POFiles that have become redundant.

    This is needed to deal with a concurrency problem where POFiles may
    get created (through message sharing) while translations are still
    being copied.
    """
    assert to_table.lower() == "pofile", (
        "This callback is meant for pouring the POFile table only.")

    params = {
        'from_table': from_table,
        'begin_id': begin_id,
        'end_id': end_id,
    }
    cursor().execute("""
        DELETE FROM %(from_table)s
        WHERE
            id >= %(begin_id)s AND
            id < %(end_id)s AND
            EXISTS (
                SELECT *
                FROM POFile
                WHERE
                    POFile.potemplate = %(from_table)s.potemplate AND
                    POFile.language = %(from_table)s.language
            )
        """ % params)


def copy_active_translations(child, transaction, logger):
    """Furnish untranslated child `DistroSeries` with previous series's
    translations.

    This method uses `MultiTableCopy` to copy data.

    Translation data for the new series ("child") is first copied into holding
    tables called e.g. "temp_POTemplate_holding_ubuntu_feisty" and processed
    there.  Then, near the end of the procedure, the contents of these holding
    tables are all poured back into the original tables.

    If this procedure fails, it may leave holding tables behind.  This was
    done deliberately to leave some forensics information for failures, and
    also to allow admins to see what data has and has not been copied.

    If a holding table left behind by an abortive run has a column called
    new_id at the end, it contains unfinished data and may as well be dropped.
    If it does not have that column, the holding table was already in the
    process of being poured back into its source table.  In that case the
    sensible thing to do is probably to continue pouring it.
    """
    previous_series = child.previous_series
    if previous_series is None:
        # We don't have a previous series from where we could copy
        # translations.
        return

    translation_tables = ['potemplate', 'translationtemplateitem', 'pofile']

    full_name = "%s_%s" % (child.distribution.name, child.name)
    copier = MultiTableCopy(full_name, translation_tables, logger=logger)

    # Incremental copy of updates is no longer supported
    assert not child.has_translation_templates, (
           "The child series must not yet have any translation templates.")

    logger.info(
        "Populating blank distroseries %s with translations from %s." %
        (child.name, previous_series.name))

    # 1. Extraction phase--for every table involved (called a "source table"
    # in MultiTableCopy parlance), we create a "holding table."  We fill that
    # with all rows from the source table that we want to copy from the
    # previous series.  We make some changes to the copied rows, such as
    # making them belong to ourselves instead of our previous series.
    #
    # The first phase does not modify any tables that other clients may want
    # to use, avoiding locking problems.
    #
    # 2. Pouring phase.  From each holding table we pour all rows back into
    # the matching source table, deleting them from the holding table as we
    # go.  The holding table is dropped once empty.
    #
    # The second phase is "batched," moving only a small number of rows at a
    # time, then performing an intermediate commit.  This avoids holding too
    # many locks for too long and disrupting regular database service.

    # Clean up any remains from a previous run.  If we got here, that means
    # that any such remains are unsalvagable.
    copier.dropHoldingTables()

    # Copy relevant POTemplates from existing series into a holding table,
    # complete with their original id fields.
    where = 'distroseries = %s AND iscurrent' % quote(previous_series)
    copier.extract('potemplate', [], where)

    # Now that we have the data "in private," where nobody else can see it,
    # we're free to play with it.  No risk of locking other processes out of
    # the database.
    # Change series identifiers in the holding table to point to the new
    # series (right now they all bear the previous series's id) and set
    # creation dates to the current transaction time.
    cursor().execute('''
        UPDATE %s
        SET
            distroseries = %s,
            datecreated =
                timezone('UTC'::text,
                    ('now'::text)::timestamp(6) with time zone)
    ''' % (copier.getHoldingTableName('potemplate'), quote(child)))

    # Copy each TranslationTemplateItem whose template we copied, and let
    # MultiTableCopy replace each potemplate reference with a reference to
    # our copy of the original POTMsgSet's potemplate.
    copier.extract('translationtemplateitem', ['potemplate'], 'sequence > 0')

    # Copy POFiles, making them refer to the child's copied POTemplates.
    copier.extract(
        'pofile', ['potemplate'],
        batch_pouring_callback=omit_redundant_pofiles)

    # Finally, pour the holding tables back into the originals.
    copier.pour(transaction)
