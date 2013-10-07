# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'ExportedFolder',
    'ExportedImageFolder',
    ]

import errno
import os
import re
import time

from zope.browserresource.file import setCacheControl
from zope.contenttype import guess_content_type
from zope.datetime import rfc1123_date
from zope.interface import implements
from zope.publisher.interfaces import NotFound
from zope.publisher.interfaces.browser import IBrowserPublisher


class File:
    # Copied from zope.browserresource.file, which
    # unbelievably throws away the file data, and isn't
    # useful extensible.
    #
    def __init__(self, path, name):
        self.path = path

        f = open(path, 'rb')
        self.data = f.read()
        f.close()
        self.content_type, enc = guess_content_type(path, self.data)
        self.__name__ = name
        self.lmt = float(os.path.getmtime(path)) or time.time()
        self.lmh = rfc1123_date(self.lmt)


class ExportedFolder:
    """View that gives access to the files in a folder.

    The URL to the folder can start with an optional path step like
    /revNNN/ where NNN is one or more digits.  This path step will
    be ignored.  It is useful for having a different path for
    all resources being served, to ensure that we don't use cached
    files in browsers.

    By default, subdirectories are not exported. Set export_subdirectories
    to True to change this.
    """

    implements(IBrowserPublisher)

    rev_part_re = re.compile('rev\d+$')

    export_subdirectories = False

    def __init__(self, context, request):
        """Initialize with context and request."""
        self.context = context
        self.request = request
        self.names = []

    def __call__(self):
        names = list(self.names)
        if names and self.rev_part_re.match(names[0]):
            # We have a /revNNN/ path step, so remove it.
            names = names[1:]

        if not names:
            # Just the root directory, so make this a 404.
            raise NotFound(self, '')
        elif len(names) > 1 and not self.export_subdirectories:
            # Too many path elements, so make this a 404.
            raise NotFound(self, self.names[-1])
        else:
            # Actually serve up the resource.
            # Don't worry about serving  up stuff like ../../../etc/passwd,
            # because the Zope name traversal will sanitize './' and '../'
            # before setting the value of self.names.
            return self.prepareDataForServing(
                os.path.join(self.folder, *names))

    def prepareDataForServing(self, filename):
        """Set the response headers and return the data for this resource."""
        name = os.path.basename(filename)
        try:
            fileobj = File(filename, name)
        except IOError as ioerror:
            expected = (errno.ENOENT, errno.EISDIR, errno.ENOTDIR)
            if ioerror.errno in expected:
                # No such file or is a directory.
                raise NotFound(self, name)
            else:
                # Some other IOError that we're not expecting.
                raise

        # TODO: Set an appropriate charset too.  There may be zope code we
        #       can reuse for this.
        response = self.request.response
        response.setHeader('Content-Type', fileobj.content_type)
        response.setHeader('Last-Modified', fileobj.lmh)
        setCacheControl(response)
        return fileobj.data

    # The following two zope methods publishTraverse and browserDefault
    # allow this view class to take control of traversal from this point
    # onwards.  Traversed names just end up in self.names.

    def publishTraverse(self, request, name):
        """Traverse to the given name."""
        # The two following constraints are enforced by the publisher.
        assert os.path.sep not in name, (
            'traversed name contains os.path.sep: %s' % name)
        assert name != '..', 'traversing to ..'
        self.names.append(name)
        return self

    def browserDefault(self, request):
        return self, ()

    @property
    def folder(self):
        raise (
            NotImplementedError,
            'Your subclass of ExportedFolder should have its own folder.')


class ExportedImageFolder(ExportedFolder):
    """ExportedFolder subclass for directory of images.

    It supports serving image files without their extension (e.g. "image1.gif"
    can be served as "image1".
    """


    # The extensions we consider.
    image_extensions = ('.png', '.gif')

    def prepareDataForServing(self, filename):
        """Serve files without their extension.

        If the requested name doesn't exist but a file exists which has
        the same base name and has an image extension, it will be served.
        """
        root, ext = os.path.splitext(filename)
        if ext == '' and not os.path.exists(root):
            for image_ext in self.image_extensions:
                if os.path.exists(root + image_ext):
                    filename = filename + image_ext
                    break
        return super(
            ExportedImageFolder, self).prepareDataForServing(filename)
