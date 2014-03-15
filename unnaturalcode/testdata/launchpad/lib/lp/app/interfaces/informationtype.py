# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'IInformationType',
    ]

from lazr.restful.declarations import exported
from zope.schema import Choice

from lp import _
from lp.app.enums import InformationType
from lp.app.interfaces.launchpad import IPrivacy


class IInformationType(IPrivacy):

    information_type = exported(Choice(
        title=_('Information Type'),
        vocabulary=InformationType,
        required=True,
        description=_('The type of data contained in this item.')
        ))
