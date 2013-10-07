# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Enumerations and related utilities used in the lp/app modules."""

__metaclass__ = type
__all__ = [
    'FREE_INFORMATION_TYPES',
    'FREE_PRIVATE_INFORMATION_TYPES',
    'InformationType',
    'NON_EMBARGOED_INFORMATION_TYPES',
    'PRIVATE_INFORMATION_TYPES',
    'PROPRIETARY_INFORMATION_TYPES',
    'PUBLIC_INFORMATION_TYPES',
    'PUBLIC_PROPRIETARY_INFORMATION_TYPES',
    'SECURITY_INFORMATION_TYPES',
    'ServiceUsage',
    'service_uses_launchpad',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )


class InformationType(DBEnumeratedType):
    """Information Type.

    The types used to control which users and teams can see various
    Launchpad artifacts, including bugs and branches.
    """

    PUBLIC = DBItem(1, """
        Public

        Everyone can see this information.
        """)

    PUBLICSECURITY = DBItem(2, """
        Public Security

        Everyone can see this security related information.
        """)

    PRIVATESECURITY = DBItem(3, """
        Private Security

       Only the security group can see this information.
        """)

    USERDATA = DBItem(4, """
        Private

        Only shared with users permitted to see private user information.
        """)

    PROPRIETARY = DBItem(5, """
        Proprietary

        Only shared with users permitted to see proprietary information.
        """)

    EMBARGOED = DBItem(6, """
        Embargoed

        Only shared with users permitted to see embargoed information.
        """)


PUBLIC_INFORMATION_TYPES = (
    InformationType.PUBLIC, InformationType.PUBLICSECURITY)

PRIVATE_INFORMATION_TYPES = (
    InformationType.PRIVATESECURITY, InformationType.USERDATA,
    InformationType.PROPRIETARY, InformationType.EMBARGOED)

NON_EMBARGOED_INFORMATION_TYPES = (
    PUBLIC_INFORMATION_TYPES +
    (InformationType.PRIVATESECURITY, InformationType.USERDATA,
     InformationType.PROPRIETARY))

SECURITY_INFORMATION_TYPES = (
    InformationType.PUBLICSECURITY, InformationType.PRIVATESECURITY)

FREE_PRIVATE_INFORMATION_TYPES = (
    InformationType.PRIVATESECURITY, InformationType.USERDATA)

FREE_INFORMATION_TYPES = (
    PUBLIC_INFORMATION_TYPES + FREE_PRIVATE_INFORMATION_TYPES)

PROPRIETARY_INFORMATION_TYPES = (
    InformationType.PROPRIETARY, InformationType.EMBARGOED)

# The information types unrelated to user data or security
PUBLIC_PROPRIETARY_INFORMATION_TYPES = (
    (InformationType.PUBLIC,) + PROPRIETARY_INFORMATION_TYPES
)


class ServiceUsage(DBEnumeratedType):
    """Launchpad application usages.

    Indication of a pillar's usage of Launchpad for the various services:
    bug tracking, translations, code hosting, blueprint, and answers.
    """

    UNKNOWN = DBItem(10, """
    Unknown

    The maintainers have not indicated usage.  This value is the default for
    new pillars.
    """)

    LAUNCHPAD = DBItem(20, """
    Launchpad

    Launchpad is used to provide this service.
    """)

    EXTERNAL = DBItem(30, """
    External

    The service is provided external to Launchpad.
    """)

    NOT_APPLICABLE = DBItem(40, """
    Not Applicable

    The pillar does not use this type of service in Launchpad or externally.
    """)


def service_uses_launchpad(usage_enum):
    return usage_enum == ServiceUsage.LAUNCHPAD
