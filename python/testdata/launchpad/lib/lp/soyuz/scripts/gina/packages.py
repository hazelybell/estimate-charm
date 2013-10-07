# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Package information classes.

This classes are responsable for fetch and hold the information inside
the sources and binarypackages.
"""

__metaclass__ = type


__all__ = [
    'BinaryPackageData',
    'DisplayNameDecodingError',
    'get_dsc_path',
    'InvalidVersionError',
    'MissingRequiredArguments',
    'PoolFileNotFound',
    'prioritymap',
    'SourcePackageData',
    ]

import glob
import os
import re
import rfc822
import shutil
import tempfile

from lp.app.validators.version import valid_debian_version
from lp.archivepublisher.diskpool import poolify
from lp.archiveuploader.changesfile import ChangesFile
from lp.archiveuploader.utils import (
    DpkgSourceError,
    extract_dpkg_source,
    )
from lp.services import encoding
from lp.services.database.constants import UTC_NOW
from lp.services.gpg.interfaces import GPGKeyAlgorithm
from lp.services.scripts import log
from lp.soyuz.enums import PackagePublishingPriority
from lp.soyuz.scripts.gina import (
    call,
    ExecutionError,
    )
from lp.soyuz.scripts.gina.changelog import parse_changelog

#
# Data setup
#

prioritymap = {
    "required": PackagePublishingPriority.REQUIRED,
    "important": PackagePublishingPriority.IMPORTANT,
    "standard": PackagePublishingPriority.STANDARD,
    "optional": PackagePublishingPriority.OPTIONAL,
    "extra": PackagePublishingPriority.EXTRA,
    # Some binarypackages ended up with priority source, apparently
    # because of a bug in dak.
    "source": PackagePublishingPriority.EXTRA,
}

GPGALGOS = dict((item.value, item.name) for item in GPGKeyAlgorithm.items)


#
# Helper functions
#

def stripseq(seq):
    return [s.strip() for s in seq]


epoch_re = re.compile(r"^\d+:")


def get_dsc_path(name, version, component, archive_root):
    pool_root = os.path.join(archive_root, "pool")
    version = epoch_re.sub("", version)
    filename = "%s_%s.dsc" % (name, version)

    # We do a first attempt using the obvious directory name, composed
    # with the component. However, this may fail if a binary is being
    # published in another component.
    pool_dir = poolify(name, component)
    fullpath = os.path.join(pool_root, pool_dir, filename)
    if os.path.exists(fullpath):
        return filename, fullpath, component

    # Do a second pass, scrubbing through all components in the pool.
    for alt_component in os.listdir(pool_root):
        if not os.path.isdir(os.path.join(pool_root, alt_component)):
            continue
        pool_dir = poolify(name, alt_component)
        fullpath = os.path.join(pool_root, pool_dir, filename)
        if os.path.exists(fullpath):
            return filename, fullpath, alt_component

    # Couldn't find the file anywhere -- too bad.
    raise PoolFileNotFound("File %s not in archive" % filename)


def unpack_dsc(package, version, component, distro_name, archive_root):
    dsc_name, dsc_path, component = get_dsc_path(package, version,
                                                 component, archive_root)
    try:
        extract_dpkg_source(dsc_path, ".", vendor=distro_name)
    except DpkgSourceError as e:
        raise ExecutionError("Error %d unpacking source" % e.result)

    version = re.sub("^\d+:", "", version)
    version = re.sub("-[^-]+$", "", version)
    source_dir = "%s-%s" % (package, version)
    return source_dir, dsc_path


def read_dsc(package, version, component, distro_name, archive_root):
    source_dir, dsc_path = unpack_dsc(package, version, component,
                                      distro_name, archive_root)

    dsc = open(dsc_path).read().strip()

    fullpath = os.path.join(source_dir, "debian", "changelog")
    changelog = None
    if os.path.exists(fullpath):
        changelog = open(fullpath).read().strip()
    else:
        log.warn("No changelog file found for %s in %s" %
                 (package, source_dir))
        changelog = None

    copyright = None
    globpath = os.path.join(source_dir, "debian", "*copyright")
    for fullpath in glob.glob(globpath):
        if not os.path.exists(fullpath):
            continue
        copyright = open(fullpath).read().strip()

    if copyright is None:
        log.warn(
            "No copyright file found for %s in %s" % (package, source_dir))
        copyright = ''

    return dsc, changelog, copyright


def parse_person(val):
    """Parse a full email address into human-readable name and address."""
    # Some addresses have commas in them, as in: "Adam C. Powell, IV
    # <hazelsct@debian.example.com>". rfc822.parseaddr seems not to
    # handle this properly, so we munge them here.
    val = val.replace(',', '')
    return rfc822.parseaddr(val)


def parse_section(v):
    if "/" in v:
        # When a "/" is found in the section, it indicates
        # component/section. We don't want to override the
        # component, since it is correctly indicated by the
        # packages/sources files.
        return v.split("/", 1)[1]
    else:
        return v


#
# Exception classes
#

class MissingRequiredArguments(Exception):
    """Missing Required Arguments Exception.

    Raised if we attempted to construct a SourcePackageData based on an
    invalid Sources.gz entry -- IOW, without all the required arguments.
    This is because we are stuck (for now) passing arguments using
    **args as some of the argument names are not valid Python identifiers
    """


class PoolFileNotFound(Exception):
    """The specified file was not found in the archive pool"""


class InvalidVersionError(Exception):
    """An invalid package version was found"""


class InvalidSourceVersionError(InvalidVersionError):
    """
    An invalid source package version was found when processing a binary
    package.
    """


class DisplayNameDecodingError(Exception):
    """Invalid unicode encountered in displayname"""


#
# Implementation classes
#

class AbstractPackageData:
    # This class represents information on a single package that was
    # obtained through the archive. This information comes from either a
    # Sources or Packages file, and is complemented by data scrubbed
    # from the corresponding pool files (the dsc, deb and tar.gz)
    archive_root = None
    package = None
    _required = None
    version = None

    # Component is something of a special case. It is set up in
    # archive.py:PackagesMap and always supplied to the constructor (and
    # only overwritten after in special cases, which I'm not sure are
    # really correct). We check it as part of _required in the
    # subclasses only as a sanity check.
    component = None

    def __init__(self):
        if self.version is None or not valid_debian_version(self.version):
            raise InvalidVersionError("%s has an invalid version: %s" %
                                      (self.package, self.version))

        absent = object()
        missing = [attr for attr in self._required if
                   getattr(self, attr, absent) is absent]
        if missing:
            raise MissingRequiredArguments(missing)

    def process_package(self, distro_name, archive_root):
        """Process the package using the files located in the archive.

        Raises PoolFileNotFound if a file is not found in the pool.
        """
        self.archive_root = archive_root

        tempdir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tempdir)
        try:
            self.do_package(distro_name, archive_root)
        finally:
            os.chdir(cwd)
        # We only rmtree if everything worked as expected; otherwise,
        # leave it around for forensics.
        shutil.rmtree(tempdir)

        self.date_uploaded = UTC_NOW
        return True

    def do_package(self, distro_name, archive_root):
        """To be provided by derived class."""
        raise NotImplementedError


class SourcePackageData(AbstractPackageData):
    """Important data relating to a given `SourcePackageRelease`."""

    # Defaults, overwritten by __init__
    directory = None

    # Defaults, potentially overwritten by __init__
    build_depends = ""
    build_depends_indep = ""
    build_conflicts = ""
    build_conflicts_indep = ""
    standards_version = ""
    section = None
    format = None

    # These arguments /must/ have been set in the Sources file and
    # supplied to __init__ as keyword arguments. If any are not, a
    # MissingRequiredArguments exception is raised.
    _required = [
        'package',
        'binaries',
        'version',
        'maintainer',
        'section',
        'architecture',
        'directory',
        'files',
        'component',
        ]

    def __init__(self, **args):
        for k, v in args.items():
            if k == 'Binary':
                self.binaries = stripseq(v.split(","))
            elif k == 'Section':
                self.section = parse_section(v)
            elif k == 'Urgency':
                urgency = v
                # This is to handle cases like:
                #   - debget: 'high (actually works)
                #   - lxtools: 'low, closes=90239'
                if " " in urgency:
                    urgency = urgency.split()[0]
                if "," in urgency:
                    urgency = urgency.split(",")[0]
                self.urgency = urgency
            elif k == 'Maintainer':
                displayname, emailaddress = parse_person(v)
                try:
                    self.maintainer = (
                        encoding.guess(displayname),
                        emailaddress,
                        )
                except UnicodeDecodeError:
                    raise DisplayNameDecodingError(
                        "Could not decode name %s" % displayname)
            elif k == 'Files':
                self.files = []
                files = v.split("\n")
                for f in files:
                    self.files.append(stripseq(f.split(" ")))
            else:
                setattr(self, k.lower().replace("-", "_"), v)

        if self.section is None:
            self.section = 'misc'
            log.warn(
                "Source package %s lacks section, assumed %r",
                self.package, self.section)

        if '/' in self.section:
            # this apparently happens with packages in universe.
            # 3dchess, for instance, uses "universe/games"
            self.section = self.section.split("/", 1)[1]

        AbstractPackageData.__init__(self)

    def do_package(self, distro_name, archive_root):
        """Get the Changelog and urgency from the package on archive.

        If successful processing of the package occurs, this method
        sets the changelog and urgency attributes.
        """
        dsc, changelog, copyright = read_dsc(
            self.package, self.version, self.component, distro_name,
            archive_root)

        self.dsc = encoding.guess(dsc)
        self.copyright = encoding.guess(copyright)
        parsed_changelog = None
        if changelog:
            parsed_changelog = parse_changelog(changelog.split('\n'))

        self.urgency = None
        self.changelog = None
        self.changelog_entry = None
        if parsed_changelog and parsed_changelog[0]:
            cldata = parsed_changelog[0]
            if 'changes' in cldata:
                if cldata["package"] != self.package:
                    log.warn("Changelog package %s differs from %s" %
                             (cldata["package"], self.package))
                if cldata["version"] != self.version:
                    log.warn("Changelog version %s differs from %s" %
                             (cldata["version"], self.version))
                self.changelog_entry = encoding.guess(cldata["changes"])
                self.changelog = changelog
                self.urgency = cldata["urgency"]
            else:
                log.warn("Changelog empty for source %s (%s)" %
                         (self.package, self.version))

    def ensure_complete(self):
        if self.format is None:
            # XXX kiko 2005-11-05: this is very funny. We care so much about
            # it here, but we don't do anything about this in handlers.py!
            self.format = "1.0"
            log.warn(
                "Invalid format in %s, assumed %r", self.package, self.format)

        if self.urgency not in ChangesFile.urgency_map:
            log.warn(
                "Invalid urgency in %s, %r, assumed %r",
                self.package, self.urgency, "low")
            self.urgency = "low"


class BinaryPackageData(AbstractPackageData):
    """This Class holds important data to a given binarypackage."""

    # These attributes must have been set by the end of the __init__ method.
    # They are passed in as keyword arguments. If any are not set, a
    # MissingRequiredArguments exception is raised.
    _required = [
        'package',
        'installed_size',
        'maintainer',
        'section',
        'architecture',
        'version',
        'filename',
        'component',
        'size',
        'md5sum',
        'description',
        'summary',
        'priority',
        ]

    # Set in __init__
    source = None
    source_version = None
    version = None
    architecture = None
    filename = None
    section = None
    priority = None

    # Defaults, optionally overwritten in __init__
    depends = ""
    suggests = ""
    recommends = ""
    conflicts = ""
    replaces = ""
    provides = ""
    pre_depends = ""
    enhances = ""
    breaks = ""
    essential = False

    # Overwritten in do_package, optionally
    shlibs = None

    source_version_re = re.compile(r'([^ ]+) +\(([^\)]+)\)')

    def __init__(self, **args):
        for k, v in args.items():
            if k == "Maintainer":
                self.maintainer = parse_person(v)
            elif k == "Essential":
                self.essential = (v == "yes")
            elif k == 'Section':
                self.section = parse_section(v)
            elif k == "Description":
                self.description = encoding.guess(v)
                summary = self.description.split("\n")[0].strip()
                if not summary.endswith('.'):
                    summary = summary + '.'
                self.summary = summary
            elif k == "Installed-Size":
                try:
                    self.installed_size = int(v)
                except ValueError:
                    raise MissingRequiredArguments("Installed-Size is "
                        "not a valid integer: %r" % v)
            else:
                setattr(self, k.lower().replace("-", "_"), v)

        if self.source:
            # We need to handle cases like "Source: myspell
            # (1:3.0+pre3.1-6)". apt-pkg kindly splits this for us
            # already, but sometimes fails.
            # XXX: dsilvers 2005-09-22: Work out why this happens and
            # file an upstream bug against python-apt once we've worked
            # it out.
            if self.source_version is None:
                match = self.source_version_re.match(self.source)
                if match:
                    self.source = match.group(1)
                    self.source_version = match.group(2)
                else:
                    # XXX kiko 2005-10-18:
                    # This is probably a best-guess and might fail.
                    self.source_version = self.version
        else:
            # Some packages have Source, some don't -- the ones that
            # don't have the same package name.
            self.source = self.package
            self.source_version = self.version

        if (self.source_version is None or
            self.source_version != self.version and
            not valid_debian_version(self.source_version)):
            raise InvalidSourceVersionError(
                "Binary package %s (%s) refers to source package %s "
                "with invalid version: %s" %
                (self.package, self.version, self.source,
                 self.source_version))

        if self.section is None:
            self.section = 'misc'
            log.warn(
                "Binary package %s lacks a section, assumed %r",
                self.package, self.section)

        if self.priority is None:
            self.priority = 'extra'
            log.warn(
                "Binary package %s lacks valid priority, assumed %r",
                self.package, self.priority)

        AbstractPackageData.__init__(self)

    def do_package(self, distro_name, archive_root):
        """Grab shared library info from .deb."""
        fullpath = os.path.join(archive_root, self.filename)
        if not os.path.exists(fullpath):
            raise PoolFileNotFound('%s not found' % fullpath)

        call("dpkg -e %s" % fullpath)
        shlibfile = os.path.join("DEBIAN", "shlibs")
        if os.path.exists(shlibfile):
            self.shlibs = open(shlibfile).read().strip()
            log.debug("Grabbing shared library info from %s" % shlibfile)
