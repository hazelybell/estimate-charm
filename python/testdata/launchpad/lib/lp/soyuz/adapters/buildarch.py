# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'determine_architectures_to_build',
    ]


from operator import attrgetter
import os
import subprocess


class DpkgArchitectureCache:
    """Cache the results of asking questions of dpkg-architecture."""

    def __init__(self):
        self._matches = {}

    def match(self, arch, wildcard):
        if (arch, wildcard) not in self._matches:
            command = ["dpkg-architecture", "-i%s" % wildcard]
            env = dict(os.environ)
            env["DEB_HOST_ARCH"] = arch
            ret = (subprocess.call(command, env=env) == 0)
            self._matches[(arch, wildcard)] = ret
        return self._matches[(arch, wildcard)]

    def findAllMatches(self, arches, wildcards):
        return [arch for arch in arches for wildcard in wildcards
                if self.match(arch, wildcard)]


dpkg_architecture = DpkgArchitectureCache()


def determine_architectures_to_build(hintlist, archive, distroseries,
                                     legal_archseries):
    """Return a list of architectures for which this publication should build.

    This function answers the question: given a list of architectures and
    an archive, what architectures should we build it for? It takes a set of
    legal distroarchseries and the distribution series for which we are
    building.

    For PPA publications we only consider architectures supported by PPA
    subsystem (`DistroArchSeries`.supports_virtualized flag).

    :param: hintlist: A string of the architectures this source package
        specifies it builds for.
    :param: archive: The `IArchive` we are building into.
    :param: distroseries: the context `DistroSeries`.
    :param: legal_archseries: a list of all initialized `DistroArchSeries`
        to be considered.
    :return: a list of `DistroArchSeries` for which the source publication in
        question should be built.
    """
    # The 'PPA supported' flag only applies to virtualized archives
    if archive.require_virtualized:
        legal_archseries = [
            arch for arch in legal_archseries if arch.supports_virtualized]
        # Cope with no virtualization support at all. It usually happens when
        # a distroseries is created and initialized, by default no
        # architecture supports its. Distro-team might take some time to
        # decide which architecture will be allowed for PPAs and queue-builder
        # will continue to work meanwhile.
        if not legal_archseries:
            return []

    legal_arch_tags = set(
        arch.architecturetag for arch in legal_archseries if arch.enabled)

    hint_archs = set(hintlist.split())
    build_tags = set(dpkg_architecture.findAllMatches(
        legal_arch_tags, hint_archs))

    # 'all' is only used as a last resort, to create an arch-indep build
    # where no builds would otherwise exist.
    if len(build_tags) == 0 and 'all' in hint_archs:
        nominated_arch = distroseries.nominatedarchindep
        if nominated_arch in legal_archseries:
            build_tags = set([nominated_arch.architecturetag])
        else:
            build_tags = set()

    sorted_archseries = sorted(
        legal_archseries, key=attrgetter('architecturetag'))
    return [arch for arch in sorted_archseries
            if arch.architecturetag in build_tags]
