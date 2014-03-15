# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'InformationTypePortletMixin',
    ]

from lazr.restful.interfaces import IJSONRequestCache

from lp.app.enums import PRIVATE_INFORMATION_TYPES
from lp.app.interfaces.informationtype import IInformationType
from lp.app.utilities import json_dump_information_types


class InformationTypePortletMixin:

    def _getContext(self):
        information_typed = IInformationType(self.context, None)
        if information_typed is None:
            return self.context
        return information_typed

    def initialize(self):
        context = self._getContext()
        if IInformationType.providedBy(context):
            cache = IJSONRequestCache(self.request)
            json_dump_information_types(
                cache,
                context.getAllowedInformationTypes(self.user))

    @property
    def information_type(self):
        context = self._getContext()
        if IInformationType.providedBy(context):
            return context.information_type.title
        return None

    @property
    def information_type_description(self):
        context = self._getContext()
        if IInformationType.providedBy(context):
            return context.information_type.description
        return None

    @property
    def information_type_css(self):
        context = self._getContext()
        if (IInformationType.providedBy(context) and
            context.information_type in PRIVATE_INFORMATION_TYPES):
            return 'sprite private'
        else:
            return 'sprite public'

    @property
    def privacy_portlet_css(self):
        context = self._getContext()
        if (IInformationType.providedBy(context) and
            context.information_type in PRIVATE_INFORMATION_TYPES):
            return 'portlet private'
        else:
            return 'portlet public'
