# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.interface import Attribute

from lp import _
from lp.services.job.interfaces.job import IJob


class ITranslationSharingJob(IJob):

    productseries = Attribute(_("The productseries of the Packaging."))

    distroseries = Attribute(_("The distroseries of the Packaging."))

    sourcepackagename = Attribute(
        _("The sourcepackagename of the Packaging."))

    potemplate = Attribute(
        _("The POTemplate to pass around as the relevant template."))
