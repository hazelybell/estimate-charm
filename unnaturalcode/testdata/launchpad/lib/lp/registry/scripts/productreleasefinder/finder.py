# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'ProductReleaseFinder'
    ]

from collections import defaultdict
from datetime import datetime
import mimetypes
import os
import re
import urllib
import urlparse

from cscvs.dircompare import path
import pytz
from zope.component import getUtility

from lp.app.validators.name import invalid_name_pattern
from lp.app.validators.version import sane_version
from lp.registry.interfaces.product import IProductSet
from lp.registry.interfaces.series import SeriesStatus
from lp.registry.model.milestone import Milestone
from lp.registry.model.product import Product
from lp.registry.model.productrelease import (
    ProductRelease,
    ProductReleaseFile,
    )
from lp.registry.model.productseries import ProductSeries
from lp.registry.scripts.productreleasefinder.filter import FilterPattern
from lp.registry.scripts.productreleasefinder.hose import Hose
from lp.services.database import (
    read_transaction,
    write_transaction,
    )
from lp.services.database.interfaces import IStore
from lp.services.librarian.model import LibraryFileAlias


processors = '|'.join([
    'all',
    'amd64',
    'arm',
    'armel',
    'i386',
    'intel',
    'hppa',
    'hurd-i386',
    'ia64',
    'm68k',
    'mips',
    'mipsel',
    'powerpc',
    's390',
    'sparc',
    ])
flavor_pattern = re.compile(r"""
    (~                                # Packaging target
     |_[a-z][a-z]_[A-Z][A-Z]          # or language version
     |_(%s)                           # or processor version
     |[\.-](win32|OSX)                # or OS version
     |\.(deb|noarch|rpm|dmg|exe|apk)  # or packaging version
    ).*                               # to the end of the string
    """ % processors, re.VERBOSE)


def extract_version(filename):
    """Return the release version of the file, or None.

    Ensure the version is compatible with Launchpad. None is returned
    if a version could not be extracted.
    """
    version = path.split_version(path.name(filename))[1]
    if version is None:
        return None
    # Tarballs pulled from a Debian-style archive often have
    # ".orig" appended to the version number.  We don't want this.
    if version.endswith('.orig'):
        version = version[:-len('.orig')]
    # Remove processor and language flavors from the version:
    # eg. _de_DE, _all, _i386.
    version = flavor_pattern.sub('', version)
    # Bug #599250. If there is no file extension after extracting
    # the version number, we have added an unknown file extension to the
    # version. Ignore this dud match.
    if filename.endswith(version):
        return None
    # Launchpad requires all versions to be lowercase. They may contain
    # letters, numbers, dots, underscores, and hyphens (a-z0-9._-).
    version = version.lower()
    version = invalid_name_pattern.sub('-', version)
    version = version.replace('+', '-')
    return version


class ProductReleaseFinder:

    def __init__(self, ztm, log):
        self.ztm = ztm
        self.log = log

    def findReleases(self):
        """Scan for new releases in all products."""
        for product_name, filters in self.getFilters():
            self.handleProduct(product_name, filters)

    @read_transaction
    def getFilters(self):
        """Build the list of products and filters.

        Returns a list of (product_name, filters) for each product in
        the database, where the filter keys are series names.
        """
        found_globs = IStore(Product).find(
            (Product.name, ProductSeries.name, ProductSeries.releasefileglob),
            Product.id == ProductSeries.productID,
            Product.active == True,
            ProductSeries.status != SeriesStatus.OBSOLETE,
            ProductSeries.releasefileglob != None
            ).order_by(Product.name)
        products_with_filters = defaultdict(list)
        last_product = None
        for product_name, series_name, glob in found_globs:
            if last_product and last_product != product_name:
                self.log.info(
                    "%s has %d series with information",
                    last_product, len(products_with_filters[last_product]))
            last_product = product_name
            filter_pattern = FilterPattern(series_name, glob)
            products_with_filters[product_name].append(filter_pattern)
        return products_with_filters.items()

    def handleProduct(self, product_name, filters):
        """Scan for tarballs and create ProductReleases for the given product.
        """
        file_names = self.getReleaseFileNames(product_name)
        hose = Hose(filters, log_parent=self.log)
        for series_name, url in hose:
            if series_name is not None:
                try:
                    self.handleRelease(
                        product_name, series_name, url, file_names)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except:
                    self.log.exception("Could not successfully process "
                                       "URL %s for %s/%s",
                                       url, product_name, series_name)
            else:
                self.log.debug("File in %s found that matched no glob: %s",
                               product_name, url)

    @read_transaction
    def getReleaseFileNames(self, product_name):
        """Return a set of all current release file names for the product."""
        found_names = IStore(Product).find(
            LibraryFileAlias.filename,
            Product.name == product_name,
            Product.id == ProductSeries.productID,
            Milestone.productseriesID == ProductSeries.id,
            ProductRelease.milestoneID == Milestone.id,
            ProductReleaseFile.productreleaseID == ProductRelease.id,
            LibraryFileAlias.id == ProductReleaseFile.libraryfileID
            )
        file_names = set(found_names)
        return file_names

    @write_transaction
    def addReleaseTarball(self, product_name, series_name, release_name,
                          filename, size, file, content_type):
        """Create a ProductRelease (if needed), and attach tarball"""
        product = getUtility(IProductSet).getByName(product_name)
        # This can match a milestone on a differnt series than the
        # one passed, since milestones (and their releases) are unique
        # to a product.
        milestone = product.getMilestone(release_name)
        if milestone is None:
            series = product.getSeries(series_name)
            milestone = series.newMilestone(release_name)
            # Deactivate the milestone since a user did not create it.
            milestone.active = False
        release = milestone.product_release
        if release is None:
            release = milestone.createProductRelease(
                owner=product.owner, datereleased=datetime.now(pytz.UTC))
            self.log.info("Created new release %s for %s/%s",
                          release_name, product_name, series_name)
        release.addReleaseFile(
            filename, file, content_type, uploader=product.owner)

    def handleRelease(self, product_name, series_name, url, file_names):
        """If the given URL looks like a release tarball, download it
        and create a corresponding ProductRelease."""
        filename = urlparse.urlsplit(url)[2]
        slash = filename.rfind("/")
        if slash != -1:
            filename = filename[slash + 1:]
        self.log.debug("Filename portion is %s", filename)

        version = extract_version(filename)
        if version is None:
            self.log.info("Unable to parse version from %s", url)
            return
        self.log.debug("Version is %s", version)
        if not sane_version(version):
            self.log.error("Version number '%s' for '%s' is not sane",
                           version, url)
            return

        if filename in file_names:
            self.log.debug("Already have a tarball for release %s", version)
            return

        mimetype, encoding = mimetypes.guess_type(url)
        self.log.debug("Mime type is %s", mimetype)
        if mimetype is None:
            mimetype = 'application/octet-stream'

        self.log.info("Downloading %s", url)
        try:
            local, headers = urllib.urlretrieve(url)
            stat = os.stat(local)
        except IOError:
            self.log.error("Download of %s failed", url)
            raise
        except OSError:
            self.log.error("Unable to stat downloaded file")
            raise

        try:
            fp = open(local, 'r')
            os.unlink(local)
            self.addReleaseTarball(product_name, series_name, version,
                                   filename, stat.st_size, fp, mimetype)
            file_names.add(filename)
        finally:
            fp.close()
