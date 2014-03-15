# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'BinaryPackageReleaseNavigation',
    'BinaryPackageView',
    ]

from apt_pkg import parse_depends

from lp.services.webapp import Navigation
from lp.services.webapp.publisher import LaunchpadView
from lp.soyuz.browser.packagerelationship import relationship_builder
from lp.soyuz.interfaces.binarypackagerelease import IBinaryPackageRelease


class BinaryPackageReleaseNavigation(Navigation):
    usedfor = IBinaryPackageRelease


class BinaryPackageView(LaunchpadView):
    """View class for BinaryPackage"""

    def _relationship_parser(self, content):
        """Wrap the relationship_builder for BinaryPackages.

        Define apt_pkg.ParseDep as a relationship 'parser' and
        IDistroArchSeries.getBinaryPackage as 'getter'.
        """
        getter = self.context.build.distro_arch_series.getBinaryPackage
        parser = parse_depends
        return relationship_builder(content, parser=parser, getter=getter)

    def depends(self):
        return self._relationship_parser(self.context.depends)

    def recommends(self):
        return self._relationship_parser(self.context.recommends)

    def conflicts(self):
        return self._relationship_parser(self.context.conflicts)

    def replaces(self):
        return self._relationship_parser(self.context.replaces)

    def suggests(self):
        return self._relationship_parser(self.context.suggests)

    def provides(self):
        return self._relationship_parser(self.context.provides)

    def pre_depends(self):
        return self._relationship_parser(self.context.pre_depends)

    def enhances(self):
        return self._relationship_parser(self.context.enhances)

    def breaks(self):
        return self._relationship_parser(self.context.breaks)
