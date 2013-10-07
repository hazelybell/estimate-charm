# Copyright 22011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.patchwebservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__metaclass__ = type
__all__ = [
    'ITemporaryBlobStorage',
    'ITemporaryStorageManager',
    ]

from lp.services.temporaryblobstorage.interfaces import (
    ITemporaryBlobStorage,
    ITemporaryStorageManager,
    )
from lp.services.webservice.apihelpers import (
    patch_operations_explicit_version,
    )

# ITemporaryBlobStorage
patch_operations_explicit_version(
    ITemporaryBlobStorage, 'beta', "getProcessedData", "hasBeenProcessed")

# ITemporaryStorageManager
patch_operations_explicit_version(
    ITemporaryStorageManager, 'beta', "fetch")
