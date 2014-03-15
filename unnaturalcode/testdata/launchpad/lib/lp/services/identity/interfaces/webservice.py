# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.patchwebservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__metaclass__ = type
__all__ = [
    'IEmailAddress',
    ]

from lp.services.identity.interfaces.emailaddress import IEmailAddress
from lp.services.webservice.apihelpers import patch_entry_explicit_version

# IEmailAddress
patch_entry_explicit_version(IEmailAddress, 'beta')
