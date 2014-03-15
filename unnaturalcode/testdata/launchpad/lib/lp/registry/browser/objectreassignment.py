# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""A view for changing the owner or registrant of an object.

This view needs to be refactored to use the Launchpad form infrastructure.
See bug 151161.
"""

__metaclass__ = type
__all__ = ["ObjectReassignmentView"]


from zope.component import getUtility
from zope.formlib.form import FormFields
from zope.formlib.interfaces import (
    ConversionError,
    WidgetInputError,
    )
from zope.schema import Choice
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.validators.name import valid_name
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.registry.interfaces.person import (
    IObjectReassignment,
    IPersonSet,
    )
from lp.services.webapp import canonical_url


class ObjectReassignmentView(LaunchpadFormView):
    """A view class used when reassigning an object that implements IHasOwner.

    By default we assume that the owner attribute is IHasOwner.owner and the
    vocabulary for the owner widget is ValidPersonOrTeam (which is the one
    used in IObjectReassignment). If any object has special needs, it'll be
    necessary to subclass ObjectReassignmentView and redefine the schema
    and/or ownerOrMaintainerAttr attributes.

    Subclasses can also specify a callback to be called after the reassignment
    takes place. This callback must accept three arguments (in this order):
    the object whose owner is going to be changed, the old owner and the new
    owner.

    Also, if the object for which you're using this view doesn't have a
    displayname or name attribute, you'll have to subclass it and define the
    contextName property in your subclass.
    """

    ownerOrMaintainerAttr = 'owner'
    ownerOrMaintainerName = 'owner'
    # Called after changing the owner if it is overridden in a subclass.
    callback = None

    schema = IObjectReassignment
    custom_widget('existing', LaunchpadRadioWidget)

    @property
    def label(self):
        """The form label."""
        return 'Change the %s of %s' % (
            self.ownerOrMaintainerName, self.contextName)

    page_title = label

    def setUpFields(self):
        super(ObjectReassignmentView, self).setUpFields()
        self.form_fields = FormFields(
            self.form_fields, self.auto_create_team_field)

    @property
    def auto_create_team_field(self):
        terms = [
            SimpleTerm('existing', token='existing',
                       title='An existing person or team'),
            SimpleTerm('new', token='new',
                       title="A new team I'm creating here"),
            ]
        return Choice(
            __name__='existing',
            title=_('This is'),
            source=SimpleVocabulary(terms),
            default='existing',
            description=_(
              "The new team's name must begin with a lower-case letter "
              "or number, and contain only letters, numbers, dots, hyphens, "
              "or plus signs."))

    @property
    def ownerOrMaintainer(self):
        return getattr(self.context, self.ownerOrMaintainerAttr)

    @property
    def contextName(self):
        return self.context.displayname or self.context.name

    @property
    def next_url(self):
        return canonical_url(self.context)

    cancel_url = next_url

    @property
    def owner_widget(self):
        return self.widgets['owner']

    @action("Change", name="change")
    def changeOwner(self, action, data):
        """Change the owner of self.context to the one choosen by the user."""
        newOwner = data['owner']
        oldOwner = getattr(self.context, self.ownerOrMaintainerAttr)
        setattr(self.context, self.ownerOrMaintainerAttr, newOwner)
        if callable(self.callback):
            self.callback(self.context, oldOwner, newOwner)

    def validateOwner(self, new_owner):
        """Check whether the new owner is acceptable for the context object.

        If it's not acceptable, display an error by calling:
          self.setFieldError(self.ownerOrMaintainerName, 'some error info')
        """
        pass

    def _validate(self, action, data):
        """Override _validate() method."""
        # Don't let widgets validate themselves, just call validate().
        self.validate(data)
        if len(self.errors) > 0:
            return self.errors
        self.validate_widgets(data)
        return self.errors

    def validate(self, data):
        """Create new team if necessary."""
        personset = getUtility(IPersonSet)
        request = self.request
        owner_name = request.form.get(self.owner_widget.name)
        if not owner_name:
            self.setFieldError(
                'owner',
                "You have to specify the name of the person/team that's "
                "going to be the new %s." % self.ownerOrMaintainerName)
            return None

        if request.form.get('field.existing') == 'existing':
            try:
                # By getting the owner using getInputValue() we make sure
                # it's valid according to the vocabulary of self.schema's
                # owner widget.
                owner = self.owner_widget.getInputValue()
            except WidgetInputError:
                self.setFieldError(
                    'owner',
                    "The person/team named '%s' is not a valid owner for %s."
                    % (owner_name, self.contextName))
                return None
            except ConversionError:
                self.setFieldError(
                    self.ownerOrMaintainerName,
                    "There's no person/team named '%s' in Launchpad."
                    % owner_name)
                return None
        else:
            if personset.getByName(owner_name):
                self.setFieldError(
                    'owner',
                    "There's already a person/team with the name '%s' in "
                    "Launchpad. Please choose a different name or select "
                    "the option to make that person/team the new owner, "
                    "if that's what you want." % owner_name)
                return None

            if not valid_name(owner_name):
                self.setFieldError(
                    'owner',
                    "'%s' is not a valid name for a team. Please make sure "
                    "it contains only the allowed characters and no spaces."
                    % owner_name)
                return None

            owner = personset.newTeam(
                self.user, owner_name, owner_name.capitalize())

        self.validateOwner(owner)
