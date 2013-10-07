# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translation access and sharing policy."""

__metaclass__ = type
__all__ = [
    'ITranslationPolicy',
    ]

from lazr.restful.declarations import exported
from lazr.restful.fields import ReferenceChoice
from zope.interface import Interface
from zope.schema import Choice

from lp import _
from lp.translations.enums import TranslationPermission
from lp.translations.interfaces.translationgroup import ITranslationGroup


class ITranslationPolicy(Interface):
    """Permissions and sharing policy for translatable pillars.

    A translation policy defines who can edit translations, and who can
    add suggestions.  (The ability to edit also implies the ability to
    enter suggestions).  Everyone else is allowed only to view the
    translations.

    The policy can "invite" the user to edit or suggest; or it can
    merely "allow" them to.  Whoever is invited is also allowed, but
    administrators and certain other special users may be allowed
    without actually being invited.

    The invitation is based purely on the access model configured by the
    user: translation team and translation policy.
    """

    translationgroup = exported(ReferenceChoice(
        title = _("Translation group"),
        description = _("The translation group that helps review "
            " translations for this project or distribution. The group's "
            " role depends on the permissions policy selected below."),
        required=False,
        vocabulary='TranslationGroup',
        schema=ITranslationGroup), as_of="devel")

    translationpermission = exported(Choice(
        title=_("Translation permissions policy"),
        description=_("The policy this project or distribution uses to "
            " balance openness and control for their translations."),
        required=True,
        vocabulary=TranslationPermission), as_of="devel")

    def getTranslationGroups():
        """List all applicable translation groups.

        This may be an empty list, or a list containing just this
        policy's translation group, or for a product that is part of a
        project group, possibly a list of two translation groups.

        If there is an inherited policy, its translation group comes
        first.  Duplicates are removed.
        """

    def getTranslators(language, store=None):
        """Find the applicable `TranslationGroup`(s) and translators.

        Zero, one, or two translation groups may apply.  Each may have a
        `Translator` for the language, with either a person or a team
        assigned.

        In the case of a product in a project group, there may be up to
        two entries.  In that case, the entry from the project group
        comes first.

        :param language: The language that you want the translators for.
        :type language: ILanguage
        :param store: Optionally a specific store to retrieve from.
        :type store: Store
        :return: A result set of zero or more tuples:
            (`TranslationGroup`, `Translator`, `Person`).  The
            translation group is always present and unique.  The person
            is present if and only if the translator is present.  The
            translator is unique if present, but the person need not be.
        """

    def getEffectiveTranslationPermission():
        """Get the effective `TranslationPermission`.

        Returns the strictest applicable permission out of
        `self.translationpermission` and any inherited
        `TranslationPermission`.
        """

    def invitesTranslationEdits(person, language):
        """Does this policy invite `person` to edit translations?

        The decision is based on the chosen `TranslationPermission`,
        `TranslationGroup`(s), the presence of a translation team, and
        `person`s membership of the translation team.

        As one extreme, the OPEN model invites editing by anyone.  The
        opposite extreme is CLOSED, which invites editing only by
        members of the applicable translation team.

        :param person: The user.
        :type person: IPerson
        :param language: The language to translate to.  This will be
            used to look up the applicable translation team(s).
        :type language: ILanguage
        """

    def invitesTranslationSuggestions(person, language):
        """Does this policy invite `person` to enter suggestions?

        Similar to `invitesTranslationEdits`, but for the activity of
        entering suggestions.  This carries less risk, so generally a
        wider public is invited to do this than to edit.
        """

    def allowsTranslationEdits(person, language):
        """Is `person` allowed to edit translations to `language`?

        Similar to `invitesTranslationEdits`, except administrators and
        in the case of Product translations, owners of the product are
        always allowed even if they are not invited.
        """

    def allowsTranslationSuggestions(person, language):
        """Is `person` allowed to enter suggestions for `language`?

        Similar to `invitesTranslationSuggestions, except administrators
        and in the case of Product translations, owners of the product
        are always allowed even if they are not invited.
        """

    def sharesTranslationsWithOtherSide(person, language,
                                        sourcepackage=None,
                                        purportedly_upstream=False):
        """Should translations be shared across `TranslationSide`s?

        Should translations to this object, as reviewed by `person`,
        into `language` be shared with the other `TranslationSide`?

        The answer depends on whether the user is invited to edit the
        translations on the other side.  Administrators and other
        specially privileged users are allowed to do that, but that
        does not automatically mean that their translations should be
        shared there.

        :param person: The `Person` providing translations.
        :param language: The `Language` being translated to.
        :param sourcepackage: When translating a `Distribution`, the
            `SourcePackage` that is being translated.
        :param purportedly_upstream: Whether `person` provides the
            translations in question as coming from upstream.
        """
