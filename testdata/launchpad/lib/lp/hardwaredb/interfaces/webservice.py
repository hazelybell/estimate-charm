# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.hardwaredb.interfaces.hwdb" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
    'IHWDBApplication',
    'IHWDevice',
    'IHWDeviceClass',
    'IHWDriver',
    'IHWDriverName',
    'IHWDriverPackageName',
    'IHWSubmission',
    'IHWSubmissionDevice',
    'IHWVendorID',
    'IllegalQuery',
    'ParameterError',
    ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.hardwaredb.interfaces.hwdb import (
    IHWDBApplication,
    IHWDevice,
    IHWDeviceClass,
    IHWDriver,
    IHWDriverName,
    IHWDriverPackageName,
    IHWSubmission,
    IHWSubmissionDevice,
    IHWVendorID,
    IllegalQuery,
    ParameterError,
    )


_schema_circular_imports
