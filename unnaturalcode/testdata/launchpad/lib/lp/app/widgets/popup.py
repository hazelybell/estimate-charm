# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Single selection widget using a popup to select one item from many."""

__metaclass__ = type

from lazr.restful.utils import safe_hasattr
import simplejson
from z3c.ptcompat import ViewPageTemplateFile
from zope.formlib.itemswidgets import (
    ItemsWidgetBase,
    SingleDataHelper,
    )
from zope.schema.interfaces import IChoice

from lp.app.browser.stringformatter import FormattersAPI
from lp.app.browser.vocabulary import (
    get_person_picker_entry_metadata,
    vocabulary_filters,
    )
from lp.services.propertycache import cachedproperty
from lp.services.webapp import canonical_url
from lp.services.webapp.escaping import structured


class VocabularyPickerWidget(SingleDataHelper, ItemsWidgetBase):
    """Wrapper for the lazr-js picker/picker.js widget."""

    __call__ = ViewPageTemplateFile('templates/form-picker.pt')

    picker_type = 'default'
    # Provide default values for the following properties in case someone
    # creates a vocab picker for a person instead of using the derived
    # PersonPicker.
    show_assign_me_button = False
    show_remove_button = False
    assign_me_text = 'Pick me'
    remove_person_text = 'Remove person'
    remove_team_text = 'Remove team'
    show_create_team_link = False

    popup_name = 'popup-vocabulary-picker'

    # Override inherited attributes for the form field.
    displayWidth = '20'
    displayMaxWidth = ''
    default = ''
    onKeyPress = ''
    style = ''
    cssClass = ''

    step_title = None
    # Defaults to self.vocabulary.displayname.
    header = None

    @cachedproperty
    def matches(self):
        """Return a list of matches (as ITokenizedTerm) to whatever the
        user currently has entered in the form.
        """
        # Pull form value using the parent class to avoid loop
        formValue = super(VocabularyPickerWidget, self)._getFormInput()
        if not formValue:
            return []

        vocab = self.vocabulary
        # Special case - if the entered value is valid, it is an object
        # rather than a string (I think this is a bug somewhere)
        if not isinstance(formValue, basestring):
            return [vocab.getTerm(formValue)]

        search_results = vocab.searchForTerms(formValue)

        if search_results.count() > 25:
            # If we have too many results to be useful in a list, return
            # an empty list.
            return []

        return search_results

    @cachedproperty
    def formToken(self):
        val = self._getFormValue()

        # We have a valid object - return the corresponding token
        if not isinstance(val, basestring):
            return self.vocabulary.getTerm(val).token

        # Just return the existing invalid token
        return val

    def inputField(self):
        d = {
            'formToken': self.formToken,
            'name': self.input_id,
            'displayWidth': self.displayWidth,
            'displayMaxWidth': self.displayMaxWidth,
            'onKeyPress': self.onKeyPress,
            'style': self.style,
            'cssClass': self.cssClass,
            }
        return structured(
            """<input type="text" value="%(formToken)s" id="%(name)s"
                         name="%(name)s" size="%(displayWidth)s"
                         maxlength="%(displayMaxWidth)s"
                         onKeyPress="%(onKeyPress)s" style="%(style)s"
                         class="%(cssClass)s" />""", **d).escapedtext

    @property
    def selected_value(self):
        """ String representation of field value associated with the picker.

        Default implementation is to return the 'name' attribute.
        """
        val = self._getFormValue()
        if val is not None and safe_hasattr(val, 'name'):
            return getattr(val, 'name')
        return None

    @property
    def selected_value_metadata(self):
        return None

    @property
    def show_widget_id(self):
        return 'show-widget-%s' % self.input_id.replace('.', '-')

    @property
    def config(self):
        return dict(
            picker_type=self.picker_type,
            selected_value=self.selected_value,
            selected_value_metadata=self.selected_value_metadata,
            header=self.header_text, step_title=self.step_title_text,
            extra_no_results_message=self.extra_no_results_message,
            assign_me_text=self.assign_me_text,
            remove_person_text=self.remove_person_text,
            remove_team_text=self.remove_team_text,
            show_remove_button=self.show_remove_button,
            show_assign_me_button=self.show_assign_me_button,
            vocabulary_name=self.vocabulary_name,
            vocabulary_filters=self.vocabulary_filters,
            input_element=self.input_id,
            show_widget_id=self.show_widget_id,
            show_create_team=self.show_create_team_link)

    @property
    def json_config(self):
        return simplejson.dumps(self.config)

    @property
    def extra_no_results_message(self):
        """Extra message when there are no results.

        Override this in subclasses.

        :return: A string that will be passed to Y.Node.create()
                 so it needs to be contained in a single HTML element.
        """
        return None

    @property
    def vocabulary_filters(self):
        """The name of the field's vocabulary."""
        choice = IChoice(self.context)
        if choice.vocabulary is None:
            # We need the vocabulary to get the supported filters.
            raise ValueError(
                "The %r.%s interface attribute doesn't have its "
                "vocabulary specified."
                % (choice.context, choice.__name__))
        return vocabulary_filters(choice.vocabulary)

    @property
    def vocabulary_name(self):
        """The name of the field's vocabulary."""
        choice = IChoice(self.context)
        if choice.vocabularyName is None:
            # The webservice that provides the results of the search
            # must be passed in the name of the vocabulary which is looked
            # up by the vocabulary registry.
            raise ValueError(
                "The %r.%s interface attribute doesn't have its "
                "vocabulary specified as a string, so it can't be loaded "
                "by the vocabulary registry."
                % (choice.context, choice.__name__))
        return choice.vocabularyName

    @property
    def header_text(self):
        return self.header or self.vocabulary.displayname

    @property
    def step_title_text(self):
        return self.step_title or self.vocabulary.step_title

    @property
    def input_id(self):
        """This is used to ensure the widget id contains only valid chars."""
        return FormattersAPI(self.name).zope_css_id()

    def chooseLink(self):
        if self.nonajax_uri is None:
            css = 'hidden'
        else:
            css = ''
        return ('<span class="%s">(<a id="%s" href="%s">'
                'Find&hellip;</a>)%s</span>') % (
            css, self.show_widget_id, self.nonajax_uri or '#',
            self.extraChooseLink() or '')

    def extraChooseLink(self):
        return None

    @property
    def nonajax_uri(self):
        """Override in subclass to specify a non-AJAX URI for the Find link.

        If None is returned, the find link will be hidden.
        """
        return None


class PersonPickerWidget(VocabularyPickerWidget):

    show_assign_me_button = True
    show_remove_button = False
    picker_type = 'person'

    @property
    def selected_value_metadata(self):
        val = self._getFormValue()
        return get_person_picker_entry_metadata(val)

    def extraChooseLink(self):
        if self.show_create_team_link:
            return ('or (<a href="/people/+newteam">'
                     'Create a new team&hellip;</a>)')
        return None

    @property
    def nonajax_uri(self):
        return '/people/'


class BugTrackerPickerWidget(VocabularyPickerWidget):

    __call__ = ViewPageTemplateFile('templates/bugtracker-picker.pt')
    link_template = """
        or (<a id="create-bugtracker-link"
        href="/bugs/bugtrackers/+newbugtracker"
        >Register an external bug tracker&hellip;</a>)
        """

    def extraChooseLink(self):
        return self.link_template

    @property
    def nonajax_uri(self):
        return '/bugs/bugtrackers/'


class SearchForUpstreamPopupWidget(VocabularyPickerWidget):
    """A SinglePopupWidget with a custom error message.

    This widget is used only when searching for an upstream that is also
    affected by a given bug as the page it links to includes a link which
    allows the user to register the upstream if it doesn't exist.
    """

    @property
    def extra_no_results_message(self):
        return ("<strong>Didn't find the project you were "
                "looking for? "
                '<a href="%s/+affects-new-product">Register it</a>.</strong>'
                % canonical_url(self.context.context))
