# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Browser views for source package builds."""

__metaclass__ = type

__all__ = [
    'SourcePackageBuildsView',
    ]


from lp.soyuz.browser.build import BuildRecordsView


class SourcePackageBuildsView(BuildRecordsView):
    """A view for (distro series) source package builds."""

    @property
    def search_name(self):
        """Direct the builds-list template to omit the name search field."""
        return False

    @property
    def default_build_state(self):
        """Default build state for sourcepackage builds.

        This overrides the default that is set on BuildRecordsView.
        """
        # None maps to "all states". The reason we display all states on
        # this page is because it's unlikely that there will be so
        # many builds that the listing will be overwhelming.
        return None
