# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Job for merging translations."""


__metaclass__ = type


__all__ = [
    'TranslationMergeJob',
    'TranslationSplitJob',
    'TranslationTemplateChangeJob',
    ]

import logging

from lazr.lifecycle.interfaces import (
    IObjectCreatedEvent,
    IObjectDeletedEvent,
    IObjectModifiedEvent,
    )
import transaction
from zope.interface import (
    classProvides,
    implements,
    )

from lp.services.config import config
from lp.services.job.interfaces.job import IRunnableJob
from lp.services.job.runner import BaseRunnableJob
from lp.translations.interfaces.translationpackagingjob import (
    ITranslationPackagingJobSource,
    )
from lp.translations.model.translationsharingjob import (
    TranslationSharingJob,
    TranslationSharingJobDerived,
    TranslationSharingJobType,
    )
from lp.translations.translationmerger import (
    TransactionManager,
    TranslationMerger,
    )
from lp.translations.utilities.translationsplitter import (
    TranslationSplitter,
    TranslationTemplateSplitter,
    )


class TranslationPackagingJob(TranslationSharingJobDerived, BaseRunnableJob):
    """Iterate through all Translation job types."""

    classProvides(ITranslationPackagingJobSource)

    _translation_packaging_job_types = []

    @staticmethod
    def _register_subclass(cls):
        TranslationSharingJobDerived._register_subclass(cls)
        job_type = getattr(cls, 'class_job_type', None)
        if job_type is not None:
            cls._translation_packaging_job_types.append(job_type)

    @classmethod
    def forPackaging(cls, packaging):
        """Create a TranslationPackagingJob for a Packaging.

        :param packaging: The `Packaging` to create the job for.
        :return: A `TranslationMergeJob`.
        """
        return cls.create(
            packaging.productseries, packaging.distroseries,
            packaging.sourcepackagename)

    @classmethod
    def iterReady(cls):
        """See `IJobSource`."""
        clause = TranslationSharingJob.job_type.is_in(
            cls._translation_packaging_job_types)
        return super(TranslationPackagingJob, cls).iterReady([clause])


class TranslationMergeJob(TranslationPackagingJob):
    """Job for merging translations between a product and sourcepackage."""

    implements(IRunnableJob)

    class_job_type = TranslationSharingJobType.PACKAGING_MERGE

    create_on_event = IObjectCreatedEvent

    config = config.ITranslationPackagingJobSource

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        if not self.distroseries.distribution.full_functionality:
            logger.info(
                'Skipping merge for unsupported distroseries "%s".' %
                self.distroseries.displayname)
            return
        logger.info(
            'Merging %s and %s', self.productseries.displayname,
            self.sourcepackage.displayname)
        tm = TransactionManager(transaction.manager, False)
        TranslationMerger.mergePackagingTemplates(
            self.productseries, self.sourcepackagename, self.distroseries, tm)


class TranslationSplitJob(TranslationPackagingJob):
    """Job for splitting translations between a product and sourcepackage."""

    implements(IRunnableJob)

    class_job_type = TranslationSharingJobType.PACKAGING_SPLIT

    create_on_event = IObjectDeletedEvent

    config = config.ITranslationPackagingJobSource

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        logger.info(
            'Splitting %s and %s', self.productseries.displayname,
            self.sourcepackage.displayname)
        TranslationSplitter(self.productseries, self.sourcepackage).split()


class TranslationTemplateChangeJob(TranslationPackagingJob):
    """Job for merging/splitting translations when template is changed."""

    implements(IRunnableJob)

    class_job_type = TranslationSharingJobType.TEMPLATE_CHANGE

    create_on_event = IObjectModifiedEvent

    config = config.ITranslationPackagingJobSource

    @classmethod
    def forPOTemplate(cls, potemplate):
        """Create a TranslationTemplateChangeJob for a POTemplate.

        :param potemplate: The `POTemplate` to create the job for.
        :return: A `TranslationTemplateChangeJob`.
        """
        return cls.create(potemplate=potemplate)

    def run(self):
        """See `IRunnableJob`."""
        logger = logging.getLogger()
        logger.info("Sanitizing translations for '%s'" % (
                self.potemplate.displayname))
        TranslationTemplateSplitter(self.potemplate).split()
        tm = TransactionManager(transaction.manager, False)
        TranslationMerger.mergeModifiedTemplates(self.potemplate, tm)
