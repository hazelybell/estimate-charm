# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.services.worlddata.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
     'ICountry',
     'ICountrySet',
     'ILanguage',
     'ILanguageSet',
     ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.services.worlddata.interfaces.country import (
    ICountry,
    ICountrySet,
    )
from lp.services.worlddata.interfaces.language import (
    ILanguage,
    ILanguageSet,
    )


_schema_circular_imports
