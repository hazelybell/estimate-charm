# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Methods required to customize the mimetypes library."""

__metaclass__ = type
__all__ = [
    'customizeMimetypes',
    ]

import mimetypes


def customizeMimetypes():
    """Initialize and extend the standard mimetypes library for our needs.

    This method is to be called before any requests are processed to ensure
    any call site that imports the standard mimetypes module will take
    advantage of these customizations.
    """
    mimetypes.init()

    # Add support for .bzip2 as well as .bz2.  Up to Python 3.2 (at least),
    # only .bz2 is present.
    mimetypes.encodings_map.setdefault('.bzip2', 'bzip2')

    # XXX: GavinPanella 2008-07-04 bug=229040: A fix has been requested
    # for Intrepid, to add .debdiff to /etc/mime.types, so we may be able
    # to remove this setting once a new /etc/mime.types has been installed
    # on the app servers. Additionally, Firefox does not display content
    # of type text/x-diff inline, so making this text/plain because
    # viewing .debdiff inline is the most common use-case.
    mimetypes.add_type('text/plain', '.debdiff')

    # Add support for Launchpad's OWL decription of its RDF metadata.
    mimetypes.add_type('application/rdf+xml', '.owl')
