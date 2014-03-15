# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Answer contact interfaces."""

__metaclass__ = type

__all__ = [
    'IAnswerContact',
    ]


from zope.interface import Interface
from zope.schema import Choice

from lp import _
from lp.services.fields import PublicPersonChoice


class IAnswerContact(Interface):
    """An answer contact.

    That's a person willing to receive notifications about all questions
    in a particular context.
    """

    person = PublicPersonChoice(
        title=_('Answer Contact'), required=False,
        description=_(
            "The person receiving notifications about all questions."),
        vocabulary='ValidPersonOrTeam')
    product = Choice(title=_('Project'), required=False,
        description=_(
            "The person wants to receive notifications about this project's "
            "questions."),
        vocabulary='Product')

    distribution = Choice(title=_('Distribution'), required=False,
        description=_(
            "The person wants to receive notifications about this "
            "distribution's questions."),
        vocabulary='Distribution')

    sourcepackagename = Choice(title=_('Source Package'), required=False,
        description=_(
            "The person wants to receive notifications about this "
            "sourcepackage's questions."),
        vocabulary='SourcePackageName')
