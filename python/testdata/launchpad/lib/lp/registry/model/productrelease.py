# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'ProductRelease',
    'ProductReleaseFile',
    'ProductReleaseSet',
    'productrelease_to_milestone',
    ]

import os
from StringIO import StringIO

from sqlobject import (
    ForeignKey,
    SQLMultipleJoin,
    StringCol,
    )
from storm.expr import (
    And,
    Desc,
    )
from storm.store import EmptyResultSet
from zope.component import getUtility
from zope.interface import implements

from lp.app.enums import InformationType
from lp.app.errors import NotFoundError
from lp.registry.errors import (
    InvalidFilename,
    ProprietaryProduct,
    )
from lp.registry.interfaces.person import (
    validate_person,
    validate_public_person,
    )
from lp.registry.interfaces.productrelease import (
    IProductRelease,
    IProductReleaseFile,
    IProductReleaseSet,
    UpstreamFileType,
    )
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.propertycache import cachedproperty
from lp.services.webapp.publisher import (
    get_raw_form_value_from_current_request,
    )


class ProductRelease(SQLBase):
    """A release of a product."""
    implements(IProductRelease)
    _table = 'ProductRelease'
    _defaultOrder = ['-datereleased']

    datereleased = UtcDateTimeCol(notNull=True)
    release_notes = StringCol(notNull=False, default=None)
    changelog = StringCol(notNull=False, default=None)
    datecreated = UtcDateTimeCol(
        dbName='datecreated', notNull=True, default=UTC_NOW)
    owner = ForeignKey(
        dbName="owner", foreignKey="Person",
        storm_validator=validate_person,
        notNull=True)
    milestone = ForeignKey(dbName='milestone', foreignKey='Milestone')

    _files = SQLMultipleJoin(
        'ProductReleaseFile', joinColumn='productrelease',
        orderBy='-date_uploaded', prejoins=['productrelease'])

    @cachedproperty
    def files(self):
        return self._files

    @property
    def version(self):
        """See `IProductRelease`."""
        return self.milestone.name

    @property
    def productseries(self):
        """See `IProductRelease`."""
        return self.milestone.productseries

    @property
    def product(self):
        """See `IProductRelease`."""
        return self.milestone.productseries.product

    @property
    def displayname(self):
        """See `IProductRelease`."""
        return self.milestone.displayname

    @property
    def title(self):
        """See `IProductRelease`."""
        return self.milestone.title

    @property
    def can_have_release_files(self):
        """See `IProductRelease`."""
        return self.product.information_type == InformationType.PUBLIC

    @staticmethod
    def normalizeFilename(filename):
        # Replace slashes in the filename with less problematic dashes.
        return filename.replace('/', '-')

    def destroySelf(self):
        """See `IProductRelease`."""
        assert self._files.count() == 0, (
            "You can't delete a product release which has files associated "
            "with it.")
        SQLBase.destroySelf(self)

    def _getFileObjectAndSize(self, file_or_data):
        """Return an object and length for file_or_data.

        :param file_or_data: A string or a file object or StringIO object.
        :return: file object or StringIO object and size.
        """
        if isinstance(file_or_data, basestring):
            file_size = len(file_or_data)
            file_obj = StringIO(file_or_data)
        else:
            assert isinstance(file_or_data, (file, StringIO)), (
                "file_or_data is not an expected type")
            file_obj = file_or_data
            start = file_obj.tell()
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            file_obj.seek(start)
        return file_obj, file_size

    def addReleaseFile(self, filename, file_content, content_type,
                       uploader, signature_filename=None,
                       signature_content=None,
                       file_type=UpstreamFileType.CODETARBALL,
                       description=None, from_api=False):
        """See `IProductRelease`."""
        if not self.can_have_release_files:
            raise ProprietaryProduct(
                "Only public projects can have download files.")
        if self.hasReleaseFile(filename):
            raise InvalidFilename
        # Create the alias for the file.
        filename = self.normalizeFilename(filename)
        # XXX: StevenK 2013-02-06 bug=1116954: We should not need to refetch
        # the file content from the request, since the passed in one has been
        # wrongly encoded.
        if from_api:
            file_content = get_raw_form_value_from_current_request(
                'file_content')
        file_obj, file_size = self._getFileObjectAndSize(file_content)

        alias = getUtility(ILibraryFileAliasSet).create(
            name=filename, size=file_size, file=file_obj,
            contentType=content_type)
        if signature_filename is not None and signature_content is not None:
            # XXX: StevenK 2013-02-06 bug=1116954: We should not need to
            # refetch the file content from the request, since the passed in
            # one has been wrongly encoded.
            if from_api:
                signature_content = get_raw_form_value_from_current_request(
                    'signature_content')
            signature_obj, signature_size = self._getFileObjectAndSize(
                signature_content)
            signature_filename = self.normalizeFilename(signature_filename)
            signature_alias = getUtility(ILibraryFileAliasSet).create(
                name=signature_filename, size=signature_size,
                file=signature_obj, contentType='application/pgp-signature')
        else:
            signature_alias = None
        return ProductReleaseFile(
            productrelease=self, libraryfile=alias, signature=signature_alias,
            filetype=file_type, description=description, uploader=uploader)

    def getFileAliasByName(self, name):
        """See `IProductRelease`."""
        for file_ in self.files:
            if file_.libraryfile.filename == name:
                return file_.libraryfile
            elif file_.signature and file_.signature.filename == name:
                return file_.signature
        raise NotFoundError(name)

    def getProductReleaseFileByName(self, name):
        """See `IProductRelease`."""
        for file_ in self.files:
            if file_.libraryfile.filename == name:
                return file_
        raise NotFoundError(name)

    def hasReleaseFile(self, name):
        """See `IProductRelease`."""
        try:
            self.getProductReleaseFileByName(name)
            return True
        except NotFoundError:
            return False


class ProductReleaseFile(SQLBase):
    """A file of a product release."""
    implements(IProductReleaseFile)

    _table = 'ProductReleaseFile'

    productrelease = ForeignKey(dbName='productrelease',
                                foreignKey='ProductRelease', notNull=True)

    libraryfile = ForeignKey(dbName='libraryfile',
                             foreignKey='LibraryFileAlias', notNull=True)

    signature = ForeignKey(dbName='signature',
                           foreignKey='LibraryFileAlias')

    filetype = EnumCol(dbName='filetype', enum=UpstreamFileType,
                       notNull=True, default=UpstreamFileType.CODETARBALL)

    description = StringCol(notNull=False, default=None)

    uploader = ForeignKey(
        dbName="uploader", foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    date_uploaded = UtcDateTimeCol(notNull=True, default=UTC_NOW)


class ProductReleaseSet(object):
    """See `IProductReleaseSet`."""
    implements(IProductReleaseSet)

    def getBySeriesAndVersion(self, productseries, version, default=None):
        """See `IProductReleaseSet`."""
        # Local import of Milestone to avoid circular imports.
        from lp.registry.model.milestone import Milestone
        store = IStore(productseries)
        # The Milestone is cached too because most uses of a ProductRelease
        # need it.
        result = store.find(
            (ProductRelease, Milestone),
            Milestone.productseries == productseries,
            ProductRelease.milestone == Milestone.id,
            Milestone.name == version)
        found = result.one()
        if found is None:
            return None
        product_release, milestone = found
        return product_release

    def getReleasesForSeries(self, series):
        """See `IProductReleaseSet`."""
        # Local import of Milestone to avoid import loop.
        from lp.registry.model.milestone import Milestone
        if len(list(series)) == 0:
            return EmptyResultSet()
        series_ids = [s.id for s in series]
        return IStore(ProductRelease).find(
            ProductRelease,
            And(ProductRelease.milestone == Milestone.id),
                Milestone.productseriesID.is_in(series_ids)).order_by(
                    Desc(ProductRelease.datereleased))

    def getFilesForReleases(self, releases):
        """See `IProductReleaseSet`."""
        releases = list(releases)
        if len(releases) == 0:
            return EmptyResultSet()
        return ProductReleaseFile.select(
            """ProductReleaseFile.productrelease IN %s""" % (
            sqlvalues([release.id for release in releases])),
            orderBy='-date_uploaded',
            prejoins=['libraryfile', 'libraryfile.content', 'productrelease'])


def productrelease_to_milestone(productrelease):
    """Adapt an `IProductRelease` to an `IMilestone`."""
    return productrelease.milestone
