# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from StringIO import StringIO

from zope.component import getUtility
from zope.contenttype import guess_content_type
from zope.formlib import form
from zope.formlib.interfaces import WidgetInputError
from zope.formlib.widget import (
    CustomWidgetFactory,
    SimpleInputWidget,
    )
from zope.formlib.widgets import FileWidget
from zope.interface import implements
from zope.schema import (
    Bytes,
    Choice,
    )
from zope.schema.interfaces import ValidationError
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.widgets.itemswidgets import LaunchpadRadioWidget
from lp.services.fields import KEEP_SAME_IMAGE
from lp.services.librarian.interfaces import (
    ILibraryFileAlias,
    ILibraryFileAliasSet,
    )
from lp.services.webapp.interfaces import IAlwaysSubmittedWidget


class LaunchpadFileWidget(FileWidget):
    """A FileWidget which doesn't enclose itself in <div> tags."""

    def _div(self, cssClass, contents, **kw):
        return contents


class ImageChangeWidget(SimpleInputWidget):
    """Widget for changing an existing image.

    This widget should be used only on edit forms.
    """

    implements(IAlwaysSubmittedWidget)

    EDIT_STYLE = 'editview'
    ADD_STYLE = 'addview'

    # The LibraryFileAlias representing the user-uploaded image, if any.
    _image_file_alias = None
    # The user-uploaded image itself, if any.
    _image = None

    def __init__(self, context, request, style):
        SimpleInputWidget.__init__(self, context, request)
        self.style = style
        fields = form.Fields(
            Choice(__name__='action', source=self._getActionsVocabulary(),
                   title=_('Action')),
            Bytes(__name__='image', title=_('Image')))
        fields['action'].custom_widget = CustomWidgetFactory(
            LaunchpadRadioWidget)
        fields['image'].custom_widget = CustomWidgetFactory(
            LaunchpadFileWidget, displayWidth=15)
        widgets = form.setUpWidgets(
            fields, self.name, context, request, ignore_request=False,
            data={'action': 'keep'})
        self.action_widget = widgets['action']
        self.image_widget = widgets['image']

    def __call__(self):
        img = self.context.getCurrentImage()
        if img is not None:
            # This widget is meant to be used only by fields which expect an
            # object implementing ILibraryFileAlias as their values.
            assert ILibraryFileAlias.providedBy(img)
            url = img.getURL()
        else:
            url = self.context.default_image_resource
        html = ('<div><img id="%s" src="%s" alt="%s" /></div>\n'
                % ('%s_current_img' % self.name, url, self.context.title))
        html += "%s\n%s" % (self.action_widget(), self.image_widget())
        return html

    def hasInput(self):
        return self.action_widget.hasInput()

    def _getActionsVocabulary(self):
        if self.style == self.ADD_STYLE:
            action_names = [
                ('keep', 'Leave as default image (you can change it later)'),
                ('change', 'Use this one')]
        elif self.style == self.EDIT_STYLE:
            if self.context.getCurrentImage() is not None:
                action_names = [('keep', 'Keep your selected image'),
                                ('delete', 'Change back to default image'),
                                ('change', 'Change to')]
            else:
                action_names = [('keep', 'Leave as default image'),
                                ('change', 'Change to')]
        else:
            raise AssertionError(
                "Style must be one of EDIT_STYLE or ADD_STYLE, got %s"
                % self.style)
        terms = [SimpleTerm(name, name, label) for name, label in action_names]
        return SimpleVocabulary(terms)

    def getInputValue(self):
        self._error = None
        action = self.action_widget.getInputValue()
        form = self.request.form_ng
        if action == 'change' and not form.getOne(self.image_widget.name):
            self._error = WidgetInputError(
                self.name, self.label,
                LaunchpadValidationError(
                    _('Please specify the image you want to use.')))
            raise self._error
        if action == "keep":
            if self.style == self.ADD_STYLE:
                # It doesn't make any sense to return KEEP_SAME_IMAGE in this
                # case, since there's nothing to keep.
                return None
            elif self.style == self.EDIT_STYLE:
                return KEEP_SAME_IMAGE
            else:
                raise AssertionError(
                    "Style must be one of EDIT_STYLE or ADD_STYLE, got %s"
                    % self.style)
        elif action == "change":
            self._image = form.getOne(self.image_widget.name)
            try:
                self.context.validate(self._image)
            except ValidationError as v:
                self._error = WidgetInputError(self.name, self.label, v)
                raise self._error
            self._image.seek(0)
            content = self._image.read()
            filename = self._image.filename
            type, dummy = guess_content_type(name=filename, body=content)

            # This method may be called more than once in a single request. If
            # that's the case here we'll simply return the cached
            # LibraryFileAlias we already have.
            existing_alias = self._image_file_alias
            if existing_alias is not None:
                assert existing_alias.filename == filename, (
                    "The existing LibraryFileAlias' name doesn't match the "
                    "given image's name.")
                assert existing_alias.content.filesize == len(content), (
                    "The existing LibraryFileAlias' size doesn't match "
                    "the given image's size.")
                assert existing_alias.mimetype == type, (
                    "The existing LibraryFileAlias' type doesn't match "
                    "the given image's type.")
                return existing_alias

            self._image_file_alias = getUtility(ILibraryFileAliasSet).create(
                name=filename, size=len(content), file=StringIO(content),
                contentType=type)
            return self._image_file_alias
        elif action == "delete":
            return None


class GotchiTiedWithHeadingWidget(ImageChangeWidget):
    """Widget for adding an image which also returns a copy of the uploaded
    image.

    If the uploaded image's width is bigger than resized_image_width or its
    height is bigger than resized_image_height, the copy image will be scaled
    down, otherwise the copy image will be the same as the original one.
    """

    resized_image_width = float(64)
    resized_image_height = float(64)

    def getInputValue(self):
        retval = ImageChangeWidget.getInputValue(self)
        if retval is None or retval is KEEP_SAME_IMAGE:
            # This is just for consistency, so that our callsites can always
            # unpack the value we return.
            return (retval, retval)

        file_alias_orig = retval
        import PIL.Image
        self._image.seek(0)
        original_content = StringIO(self._image.read())
        image = PIL.Image.open(original_content)
        width, height = image.size
        if (width <= self.resized_image_width and
            height <= self.resized_image_height):
            # No resize needed.
            content = original_content
        else:
            # Get the new (width, height), keeping the original scale.
            if width > height:
                new_width = self.resized_image_width
                new_height = (self.resized_image_height / width) * height
            else:
                new_height = self.resized_image_height
                new_width = (self.resized_image_width / height) * width

            new_image = image.resize(
                (int(new_width), int(new_height)), PIL.Image.ANTIALIAS)
            content = StringIO()
            format = None
            for key, mime in PIL.Image.MIME.items():
                if mime == file_alias_orig.mimetype:
                    format = key
                    break
            assert format is not None, (
                "No format found for mimetype '%s'" % file_alias_orig.mimetype)
            new_image.save(content, format=format)

        content.seek(0)
        file_alias_small = getUtility(ILibraryFileAliasSet).create(
            name=file_alias_orig.filename, size=content.len,
            file=content, contentType=file_alias_orig.mimetype)
        return file_alias_orig, file_alias_small

