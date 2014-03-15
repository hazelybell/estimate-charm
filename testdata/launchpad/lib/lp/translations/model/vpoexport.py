# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database class to handle translation export view."""

__metaclass__ = type

__all__ = [
    'VPOExportSet',
    'VPOExport'
    ]

from storm.expr import (
    And,
    Or,
    )
from zope.interface import implements

from lp.services.database.interfaces import ISlaveStore
from lp.soyuz.model.component import Component
from lp.soyuz.model.publishing import SourcePackagePublishingHistory
from lp.translations.interfaces.vpoexport import (
    IVPOExport,
    IVPOExportSet,
    )
from lp.translations.model.pofile import POFile
from lp.translations.model.potemplate import POTemplate


class VPOExportSet:
    """Retrieve collections of `VPOExport` objects."""

    implements(IVPOExportSet)

    def get_distroseries_pofiles(self, series, date=None, component=None,
                                 languagepack=None):
        """See `IVPOExport`.

        Selects `POFiles` based on the 'series', last modified 'date',
        archive 'component', and whether it belongs to a 'languagepack'
        """
        tables = [
            POFile,
            POTemplate,
            ]

        conditions = [
            POTemplate.distroseries == series,
            POTemplate.iscurrent == True,
            POFile.potemplate == POTemplate.id,
            ]

        if date is not None:
            conditions.append(Or(
                POTemplate.date_last_updated > date,
                POFile.date_changed > date))

        if component is not None:
            tables.extend([
                SourcePackagePublishingHistory,
                Component,
                ])
            conditions.extend([
                SourcePackagePublishingHistory.distroseries == series,
                SourcePackagePublishingHistory.component == Component.id,
                POTemplate.sourcepackagename ==
                    SourcePackagePublishingHistory.sourcepackagenameID,
                Component.name == component,
                SourcePackagePublishingHistory.dateremoved == None,
                SourcePackagePublishingHistory.archive == series.main_archive,
                ])

        if languagepack:
            conditions.append(POTemplate.languagepack == True)

        # Use the slave store.  We may want to write to the distroseries
        # to register a language pack, but not to the translation data
        # we retrieve for it.
        query = ISlaveStore(POFile).using(*tables).find(
            POFile, And(*conditions))

        # Order by POTemplate.  Caching in the export scripts can be
        # much more effective when consecutive POFiles belong to the
        # same POTemplate, e.g. they'll have the same POTMsgSets.
        sort_list = [POFile.potemplateID, POFile.languageID]
        return query.order_by(sort_list).config(distinct=True)

    def get_distroseries_pofiles_count(self, series, date=None,
                                        component=None, languagepack=None):
        """See `IVPOExport`."""
        return self.get_distroseries_pofiles(
            series, date, component, languagepack).count()


class VPOExport:
    """Present translations in a form suitable for efficient export."""
    implements(IVPOExport)

    potemplate = None
    languagepack = None
    pofile = None

    potmsgset_id = None
    potmsgset = None
    msgid_singular = None
    msgid_plural = None
    source_comment = None
    file_references = None
    flags_comment = None
    context = None

    def __init__(self, *args):
        """Store raw data as given in `VPOExport.column_names`."""
        (self.potmsgset_id,
         self.sequence,
         self.comment,
         self.is_current_ubuntu,
         self.is_current_upstream,
         self.diverged,
         self.translation0,
         self.translation1,
         self.translation2,
         self.translation3,
         self.translation4,
         self.translation5) = args

    def setRefs(self, pofile, potmsgsets_lookup):
        """Store various object references.

        :param pofile: the `POFile` that this export is for.
        :param potmsgsets_lookup: a dict mapping numeric ids to `POTMsgSet`s.
            This saves the ORM the job of fetching them one by one as other
            objects refer to them.
        """
        template = pofile.potemplate
        self.potemplate = template
        self.pofile = pofile

        potmsgset = potmsgsets_lookup[self.potmsgset_id]
        self.potmsgset = potmsgset

        if potmsgset.msgid_singular is not None:
            self.msgid_singular = potmsgset.msgid_singular.msgid
        if potmsgset.msgid_plural is not None:
            self.msgid_plural = potmsgset.msgid_plural.msgid

        self.source_comment = potmsgset.sourcecomment
        self.file_references = potmsgset.filereferences
        self.flags_comment = potmsgset.flagscomment
        self.context = potmsgset.context

        if potmsgset.is_translation_credit:
            self.translation0 = pofile.prepareTranslationCredits(potmsgset)
