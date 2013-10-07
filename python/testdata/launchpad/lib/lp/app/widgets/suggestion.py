# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Widgets related to IBranch."""

__metaclass__ = type
__all__ = [
    'RecipeOwnerWidget',
    'TargetBranchWidget',
    ]


from datetime import (
    datetime,
    timedelta,
    )

from pytz import utc
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.formlib.interfaces import (
    IInputWidget,
    InputErrors,
    )
from zope.formlib.utility import setUpWidget
from zope.formlib.widget import renderElement
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import (
    html_escape,
    structured,
    )
from lp.services.webapp.interfaces import ILaunchBag


class SuggestionWidget(LaunchpadRadioWidget):
    """Base class for widgets that suggest values.

    Users can pick a suggested value from a radio button list, or use the
    normal widget to pick any value they could normally pick.
    """

    def __init__(self, field, vocabulary, request):
        # Create the vocabulary and pass that to the radio button
        # constructor.
        self.suggestion_vocab = self._generateSuggestionVocab(
            field.context, vocabulary)

        LaunchpadRadioWidget.__init__(
            self, field, self.suggestion_vocab, request)

        self.other_selection_widget = getMultiAdapter(
            (field, request), IInputWidget)
        setUpWidget(
            self, 'other_selection', field, IInputWidget,
            prefix=self.name, context=field.context)

        # If there are suggestions to show explicitly, then we want to select
        # the 'Other' selection item when the user chooses a non-suggested
        # value.
        if self._shouldRenderSuggestions():
            self._autoselectOther()

    @classmethod
    def _generateSuggestionVocab(cls, context, full_vocabulary):
        """Generate a vocabulary for the suggestions.

        :param context: The context object to generate suggestions for.
        :param full_vocabulary: The vocabulary suggestions may be drawn from.
            suggestions not present in this vocabulary are ignored.
        """
        suggestions = cls._getSuggestions(context)
        terms = [
            term for term in full_vocabulary
            if term.value in suggestions]
        return SimpleVocabulary(terms)

    def _shouldRenderSuggestions(self):
        """Return True if suggestions should be rendered."""
        return len(self.suggestion_vocab) > 0

    def _optionId(self, index):
        return '%s.%d' % (html_escape(self.name), index)

    def _otherId(self):
        """Return the id of the "Other" option."""
        return self._optionId(len(self.suggestion_vocab))

    def _toFieldValue(self, form_value):
        """Convert the form value into the target value.

        If there were no radio button options, or 'other' was selected, then
        get the value from the other_selection widget, otherwise get the
        object reference from the built up vocabulary.
        """
        if not self._shouldRenderSuggestions() or form_value == "other":
            # Get the value from the other selector widget.
            try:
                return self.other_selection_widget.getInputValue()
            except InputErrors:
                self._error = self.other_selection_widget._error
                raise
        else:
            term = self.suggestion_vocab.getTermByToken(form_value)
            return term.value

    def hasInput(self):
        """Is there any input for the widget.

        We need to defer the call to the other widget when either there are no
        terms in the vocabulary or the other radio button was selected.
        """
        if not self._shouldRenderSuggestions():
            return self.other_selection_widget.hasInput()
        else:
            has_input = LaunchpadRadioWidget.hasInput(self)
            if has_input:
                if self._getFormInput() == "other":
                    return self.other_selection_widget.hasInput()
            return has_input

    def getInputValue(self):
        """Return the branch defined by the input value."""
        return self._toFieldValue(self._getFormInput())

    def setRenderedValue(self, value):
        """This widget does not support setting the value."""
        pass

    def _renderLabel(self, text, index):
        """Render a label for the option with the specified index."""
        label = structured(
            u'<label for="%s" style="font-weight: normal">%s</label>',
            self._optionId(index), text)
        return label

    def _renderSuggestionLabel(self, value, index):
        """Render a label for the option based on a branch."""
        return self._renderLabel(self._valueDisplayname(value), index)

    @staticmethod
    def _valueDisplayname(value):
        """Return the displayname for a value."""
        return value.displayname

    def renderItems(self, value):
        """Render the items for the selector."""
        field = self.context
        if value == self._missing:
            value = field.missing_value

        items = []
        index = 0
        # Render each of the suggestions with the first selected.
        for index, term in enumerate(self.suggestion_vocab):
            suggestion = term.value
            if index == 0:
                renderfunc = self.renderSelectedItem
            else:
                renderfunc = self.renderItem
            text = self._renderSuggestionLabel(suggestion, index)
            render_args = dict(
                index=index, text=text, value=term.token,
                name=self.name, cssClass=self.cssClass)
            items.append(renderfunc(**render_args))

        # Lastly render the other option.
        index = len(items)
        other_selection_text = "%s %s" % (
            html_escape(self._renderLabel("Other:", index)),
            self.other_selection_widget())
        other_selection_onclick = (
            "this.form['%s'].focus()" % self.other_selection_widget.name)

        elem = renderElement(u'input',
                             value="other",
                             name=self.name,
                             id='%s.%s' % (self.name, index),
                             cssClass=self.cssClass,
                             type='radio',
                             onClick=other_selection_onclick)

        other_radio_button = '%s&nbsp;%s' % (elem, other_selection_text)

        items.append(other_radio_button)

        return items

    def __call__(self):
        """Don't render the radio buttons if only one choice."""
        if not self._shouldRenderSuggestions():
            return self.other_selection_widget()
        else:
            return LaunchpadRadioWidget.__call__(self)


class TargetBranchWidget(SuggestionWidget):
    """Widget for selecting a target branch.

    The default branch for a new branch merge proposal should be
    the branch associated with the development focus series if there
    is one (that isn't an import branch).

    Also in the initial radio button selector are other branches for
    the product that the branch owner has specified as target branches
    for other merge proposals.

    Finally there is an "other" button that gets the user to use the
    normal branch selector.
    """

    @staticmethod
    def _generateSuggestionVocab(branch, full_vocabulary):
        """Generate the vocabulary for the radio buttons.

        The generated vocabulary contains the branch associated with the
        development series of the product if there is one, and also any other
        branches that the user has specified before as a target for a proposed
        merge.
        """
        default_target = branch.target.default_merge_target
        logged_in_user = getUtility(ILaunchBag).user
        since = datetime.now(utc) - timedelta(days=90)
        collection = branch.target.collection.targetedBy(logged_in_user,
            since)
        collection = collection.visibleByUser(logged_in_user)
        # May actually need some eager loading, but the API isn't fine grained
        # yet.
        branches = collection.getBranches(eager_load=False).config(distinct=True)
        target_branches = list(branches.config(limit=5))
        # If there is a development focus branch, make sure it is always
        # shown, and as the first item.
        if default_target is not None:
            if default_target in target_branches:
                target_branches.remove(default_target)
            target_branches.insert(0, default_target)

        # Make sure the source branch isn't in the target_branches.
        if branch in target_branches:
            target_branches.remove(branch)

        terms = []
        for branch in target_branches:
            terms.append(SimpleTerm(
                    branch, branch.unique_name))

        return SimpleVocabulary(terms)

    def _renderSuggestionLabel(self, branch, index):
        """Render a label for the option based on a branch."""
        # To aid usability there needs to be some text connected with the
        # radio buttons that is not a hyperlink in order to select the radio
        # button.  It was decided not to have the entire text as a link, but
        # instead to have a separate link to the branch details.
        text = '%s (<a href="%s">branch details</a>)' % (
            html_escape(branch.displayname),
            html_escape(canonical_url(branch)))
        # If the branch is the development focus, say so.
        if branch == self.context.context.target.default_merge_target:
            text = text + "&ndash; <em>development focus</em>"
        label = u'<label for="%s" style="font-weight: normal">%s</label>' % (
            self._optionId(index), text)
        return structured(label)

    def _autoselectOther(self):
        """Select "other" on keypress."""
        on_key_press = "selectWidget('%s', event);" % self._otherId()
        self.other_selection_widget.onKeyPress = on_key_press


class RecipeOwnerWidget(SuggestionWidget):
    """Widget for selecting a recipe owner.

    The current user and the base branch owner are suggested.
    """

    @staticmethod
    def _getSuggestions(branch):
        """Suggest the branch owner and current user."""
        logged_in_user = getUtility(ILaunchBag).user
        return set([branch.owner, logged_in_user])

    @staticmethod
    def _valueDisplayname(value):
        """Provide a specialized displayname for Persons"""
        return value.unique_displayname

    def _autoselectOther(self):
        """Select "other" on click."""
        on_click = "onClick=\"selectWidget('%s', event);\"" % self._otherId()
        self.other_selection_widget.extra = on_click
