# Copyright 2009, 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""All the interfaces that are exposed through the webservice.

There is a declaration in ZCML somewhere that looks like:
  <webservice:register module="lp.translations.interfaces.webservice" />

which tells `lazr.restful` that it should look for webservice exports here.
"""

__all__ = [
    'IHasTranslationImports',
    'IPOFile',
    'IPOTemplate',
    'ITranslationGroup',
    'ITranslationImportQueue',
    'ITranslationImportQueueEntry',
    ]

# XXX: JonathanLange 2010-11-09 bug=673083: Legacy work-around for circular
# import bugs.  Break this up into a per-package thing.
from lp import _schema_circular_imports
from lp.translations.interfaces.hastranslationimports import (
    IHasTranslationImports,
    )
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.translationgroup import (
    ITranslationGroup,
    ITranslationGroupSet,
    )
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    ITranslationImportQueueEntry,
    )


_schema_circular_imports
