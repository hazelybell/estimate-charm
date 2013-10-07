# Copyright 2010 Canonical Ltd. This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'ITranslationTemplatesBuildJobSource',
    ]

from zope.interface import Interface


class ITranslationTemplatesBuildJobSource(Interface):
    """Container for `TranslationTemplatesBuildJob`s."""

    def generatesTemplates(branch):
        """Can this branch usefully generate translation templates?

        If yes, then use `create` to schedule a build-farm job to
        generate the templates based on the source code in the branch.
        """

    def create(branch):
        """Create new `TranslationTemplatesBuildJob`.

        Also creates the matching `IBuildQueue` and `IJob`.

        :param branch: A `Branch` that this job will check out and
            generate templates for.
        :return: A new `TranslationTemplatesBuildJob`.
        """

    def scheduleTranslationTemplatesBuild(branch):
        """Schedule a translation templates build job, if appropriate."""

    def getByBranch(branch):
        """Find `TranslationTemplatesBuildJob` for given `Branch`."""
