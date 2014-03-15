# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'AnnouncementDate',
    'FormattableDate',
    'BaseImageUpload',
    'BlacklistableContentNameField',
    'BugField',
    'ContentNameField',
    'Description',
    'Datetime',
    'DuplicateBug',
    'FieldNotBoundError',
    'IAnnouncementDate',
    'IBaseImageUpload',
    'IBugField',
    'IDescription',
    'ILocationField',
    'INoneableTextLine',
    'IPersonChoice',
    'IStrippedTextLine',
    'ISummary',
    'ITag',
    'ITimeInterval',
    'ITitle',
    'IURIField',
    'IWhiteboard',
    'IconImageUpload',
    'KEEP_SAME_IMAGE',
    'LocationField',
    'LogoImageUpload',
    'MugshotImageUpload',
    'NoneableDescription',
    'NoneableTextLine',
    'PersonChoice',
    'PillarAliases',
    'PillarNameField',
    'PrivateMembershipTeamNotAllowed',
    'PrivateTeamNotAllowed',
    'ProductBugTracker',
    'ProductNameField',
    'PublicPersonChoice',
    'SearchTag',
    'StrippedTextLine',
    'Summary',
    'Tag',
    'TimeInterval',
    'Title',
    'URIField',
    'UniqueField',
    'Whiteboard',
    'WorkItemsText',
    'is_public_person_or_closed_team',
    'is_public_person',
    ]


import re
from StringIO import StringIO
from textwrap import dedent

from lazr.restful.fields import Reference
from lazr.restful.interfaces import IReferenceChoice
from lazr.uri import (
    InvalidURIError,
    URI,
    )
from zope.component import getUtility
from zope.interface import implements
from zope.schema import (
    Bool,
    Bytes,
    Choice,
    Date,
    Datetime,
    Field,
    Float,
    Int,
    Text,
    TextLine,
    Tuple,
    )
from zope.schema.interfaces import (
    ConstraintNotSatisfied,
    IBytes,
    IDate,
    IDatetime,
    IField,
    Interface,
    IObject,
    IText,
    ITextLine,
    )
from zope.security.interfaces import ForbiddenAttribute

from lp import _
from lp.app.validators import LaunchpadValidationError
from lp.app.validators.name import (
    name_validator,
    valid_name,
    )
from lp.blueprints.enums import SpecificationWorkItemStatus
from lp.bugs.errors import InvalidDuplicateValue
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    PersonVisibility,
    )
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.services.webapp.interfaces import ILaunchBag

# Marker object to tell BaseImageUpload to keep the existing image.
KEEP_SAME_IMAGE = object()
# Regexp for detecting milestone headers in work items text.
MILESTONE_RE = re.compile('^work items(.*)\s*:\s*$', re.I)
# Regexp for work items.
WORKITEM_RE = re.compile(
    '^(\[(?P<assignee>.*?)\])?\s*(?P<title>.*)\s*:\s*(?P<status>.*)\s*$', re.I)


# Field Interfaces

class IStrippedTextLine(ITextLine):
    """A field with leading and trailing whitespaces stripped."""


class ITitle(IStrippedTextLine):
    """A Field that implements a launchpad Title"""


class INoneableTextLine(IStrippedTextLine):
    """A field that is None if it's value is empty or whitespace."""


class ISummary(IText):
    """A Field that implements a Summary"""


class IDescription(IText):
    """A Field that implements a Description"""


class INoneableDescription(IDescription):
    """A field that is None if it's value is empty or whitespace."""


class IWhiteboard(IText):
    """A Field that implements a Whiteboard"""


class ITimeInterval(ITextLine):
    """A field that captures a time interval in days, hours, minutes."""


class IBugField(IObject):
    """A field that allows entry of a Bug number or nickname"""


class IAnnouncementDate(IDatetime):
    """Marker interface for AnnouncementDate fields.

    This is used in cases where we either want to publish something
    immediately, or come back in future to publish it, or set a date for
    publication in advance. Essentially this amounts to a Datetime that can
    be None.
    """


class ILocationField(IField):
    """A location, consisting of geographic coordinates and a time zone."""

    latitude = Float(title=_('Latitude'))
    longitude = Float(title=_('Longitude'))
    time_zone = Choice(title=_('Time zone'), vocabulary='TimezoneName')


class ITag(ITextLine):
    """A tag.

    A text line which can be used as a simple text tag.
    """


class IURIField(ITextLine):
    """A URI.

    A text line that holds a URI.
    """
    trailing_slash = Bool(
        title=_('Whether a trailing slash is required for this field'),
        required=False,
        description=_('If set to True, then the path component of the URI '
                      'will be automatically normalized to end in a slash. '
                      'If set to False, any trailing slash will be '
                      'automatically removed. If set to None, URIs will '
                      'not be normalized.'))

    def normalize(input):
        """Normalize a URI.

         * whitespace is stripped from the input value
         * if the field requires (or forbids) a trailing slash on the URI,
           ensures that the widget ends in a slash (or doesn't end in a
           slash).
         * the URI is canonicalized.
         """


class IBaseImageUpload(IBytes):
    """Marker interface for ImageUpload fields."""

    dimensions = Tuple(
        title=_('Maximum dimensions'),
        description=_('A two-tuple with the maximum width and height (in '
                      'pixels) of this image.'))
    max_size = Int(
        title=_('Maximum size'),
        description=_('The maximum size (in bytes) of this image.'))

    default_image_resource = TextLine(
        title=_('The default image'),
        description=_(
            'The URL of the zope3 resource of the default image that should '
            'be used. Something of the form /@@/team-mugshot'))

    def getCurrentImage():
        """Return the value of the field for the object bound to it.

        Raise FieldNotBoundError if the field is not bound to any object.
        """


class StrippedTextLine(TextLine):
    implements(IStrippedTextLine)

    def set(self, object, value):
        """Strip the value and pass up."""
        if value is not None:
            value = value.strip()
        super(StrippedTextLine, self).set(object, value)


class NoneableTextLine(StrippedTextLine):
    implements(INoneableTextLine)


# Title
# A field to capture a launchpad object title

class Title(StrippedTextLine):
    implements(ITitle)


class StrippableText(Text):
    """A text that can be configured to strip when setting."""

    def __init__(self, strip_text=False, trailing_only=False, **kwargs):
        super(StrippableText, self).__init__(**kwargs)
        self.strip_text = strip_text
        self.trailing_only = trailing_only

    def normalize(self, value):
        """Strip the leading and trailing whitespace."""
        if self.strip_text and value is not None:
            if self.trailing_only:
                value = value.rstrip()
            else:
                value = value.strip()
        return value

    def set(self, object, value):
        """Strip the value and pass up."""
        value = self.normalize(value)
        super(StrippableText, self).set(object, value)

    def validate(self, value):
        """See `IField`."""
        value = self.normalize(value)
        return super(StrippableText, self).validate(value)


# Summary
# A field capture a Launchpad object summary

class Summary(StrippableText):
    implements(ISummary)


# Description
# A field capture a Launchpad object description

class Description(StrippableText):
    implements(IDescription)


class NoneableDescription(Description):
    implements(INoneableDescription)


# Whiteboard
# A field capture a Launchpad object whiteboard

class Whiteboard(StrippableText):
    implements(IWhiteboard)


class FormattableDate(Date):
    """A datetime field that checks for compatibility with Python's strformat.

    From the user's perspective this is a date entry field; it converts to and
    from datetime because that's what the db is expecting.
    """
    implements(IDate)

    def _validate(self, value):
        error_msg = ("Date could not be formatted. Provide a date formatted "
            "like YYYY-MM-DD format. The year must be after 1900.")

        super(FormattableDate, self)._validate(value)
        # The only thing of interest here is whether or the input can be
        # formatted properly, not whether it makes sense otherwise.
        # As a minimal sanity check, just raise an error if it fails.
        try:
            value.strftime('%Y')
        except ValueError:
            raise LaunchpadValidationError(error_msg)


class AnnouncementDate(Datetime):
    implements(IDatetime)


# TimeInterval
# A field to capture an interval in time, such as X days, Y hours, Z
# minutes.

class TimeInterval(TextLine):
    implements(ITimeInterval)

    def _validate(self, value):
        if 'mon' in value:
            return 0
        return 1


class BugField(Reference):
    implements(IBugField)

    def __init__(self, *args, **kwargs):
        """The schema will always be `IBug`."""
        super(BugField, self).__init__(Interface, *args, **kwargs)

    def _get_schema(self):
        """Get the schema here to avoid circular imports."""
        from lp.bugs.interfaces.bug import IBug
        return IBug

    def _set_schema(self, schema):
        """Ignore attempts to set the schema by the superclass."""

    schema = property(_get_schema, _set_schema)


# XXX: Tim Penhey 2011-01-21 bug 706099
# Should have bug specific fields in lp.services.fields
class DuplicateBug(BugField):
    """A bug that the context is a duplicate of."""

    def _validate(self, value):
        """Prevent dups of dups.

        Returns True if the dup target is not a duplicate /and/ if the
        current bug doesn't have any duplicates referencing it /and/ if the
        bug isn't a duplicate of itself, otherwise
        return False.
        """
        current_bug = self.context
        dup_target = value
        if current_bug == dup_target:
            raise InvalidDuplicateValue(_(dedent("""
                You can't mark a bug as a duplicate of itself.""")))
        elif dup_target.duplicateof is not None:
            raise InvalidDuplicateValue(_(dedent("""
                Bug ${dup} is already a duplicate of bug ${orig}. You
                can only mark a bug report as duplicate of one that
                isn't a duplicate itself.
                """), mapping={'dup': dup_target.id,
                               'orig': dup_target.duplicateof.id}))
        else:
            return True


class Tag(TextLine):

    implements(ITag)

    def constraint(self, value):
        """Make sure that the value is a valid name."""
        super_constraint = TextLine.constraint(self, value)
        return super_constraint and valid_name(value)


class SearchTag(Tag):

    def constraint(self, value):
        """Make sure the value is a valid search tag.

        A valid search tag is a valid name or a valid name prepended
        with a minus, denoting "not this tag". A simple wildcard - an
        asterisk - is also valid, with or without a leading minus.
        """
        if value in ('*', '-*'):
            return True
        elif value.startswith('-'):
            return super(SearchTag, self).constraint(value[1:])
        else:
            return super(SearchTag, self).constraint(value)


class UniqueField(TextLine):
    """Base class for fields that are used for unique attributes."""

    errormessage = _("%s is already taken")
    attribute = None

    @property
    def _content_iface(self):
        """Return the content interface.

        Override this in subclasses.
        """
        return None

    def _getByAttribute(self, input):
        """Return the content object with the given attribute.

        Override this in subclasses.
        """
        raise NotImplementedError

    def _isValueTaken(self, value):
        """Returns true if and only if the specified value is already taken.
        """
        return self._getByAttribute(value) is not None

    def unchanged(self, input):
        """Return True if the attribute on the object is unchanged."""
        _marker = object()
        if (self._content_iface.providedBy(self.context) and
            input == getattr(self.context, self.attribute, _marker)):
            return True
        return False

    def _validate(self, input):
        """Raise a LaunchpadValidationError if the attribute is not available.

        A attribute is not available if it's already in use by another
        object of this same context. The 'input' should be valid as per
        TextLine.
        """
        super(UniqueField, self)._validate(input)
        assert self._content_iface is not None

        if self.unchanged(input):
            # The value is not being changed, thus it already existed, so we
            # know it is unique.
            return

        # Now we know we are dealing with either a new object, or an
        # object whose attribute is going to be updated. We need to
        # ensure the new value is unique.
        if self._isValueTaken(input):
            raise LaunchpadValidationError(self.errormessage % input)


class ContentNameField(UniqueField):
    """Base class for fields that are used by unique 'name' attributes."""

    attribute = 'name'

    def _getByAttribute(self, input):
        """Return the content object with the given attribute."""
        return self._getByName(input)

    def _getByName(self, input):
        """Return the content object with the given name.

        Override this in subclasses.
        """
        raise NotImplementedError

    def _validate(self, name):
        """Check that the given name is valid (and by delegation, unique)."""
        name_validator(name)
        UniqueField._validate(self, name)


class BlacklistableContentNameField(ContentNameField):
    """ContentNameField that also checks that a name is not blacklisted"""

    blacklistmessage = _("The name '%s' has been blocked by the Launchpad "
                         "administrators. Contact Launchpad Support if you "
                         "want to use this name.")

    def _validate(self, input):
        """Check that the given name is valid, unique and not blacklisted."""
        super(BlacklistableContentNameField, self)._validate(input)

        # Although this check is performed in UniqueField._validate(), we need
        # to do it here again to avoid checking whether or not the name is
        # blacklisted when it hasn't been changed.
        if self.unchanged(input):
            # The attribute wasn't changed.
            return

        # Need a local import because of circular dependencies.
        from lp.registry.interfaces.person import IPersonSet
        user = getUtility(ILaunchBag).user
        if getUtility(IPersonSet).isNameBlacklisted(input, user):
            raise LaunchpadValidationError(self.blacklistmessage % input)


class PillarAliases(TextLine):
    """A field which takes a list of space-separated aliases for a pillar."""

    def _split_input(self, input):
        if input is None:
            return []
        return re.sub(r'\s+', ' ', input).split()

    def _validate(self, input):
        """Make sure all the aliases are valid for the field's pillar.

        An alias is valid if it can be used as the name of a pillar and is
        not identical to the pillar's existing name.
        """
        context = self.context
        from lp.registry.interfaces.product import IProduct
        from lp.registry.interfaces.projectgroup import IProjectGroup
        from lp.registry.interfaces.distribution import IDistribution
        if IProduct.providedBy(context):
            name_field = IProduct['name']
        elif IProjectGroup.providedBy(context):
            name_field = IProjectGroup['name']
        elif IDistribution.providedBy(context):
            name_field = IDistribution['name']
        else:
            raise AssertionError("Unexpected context type.")
        name_field.bind(context)
        existing_aliases = context.aliases
        for name in self._split_input(input):
            if name == context.name:
                raise LaunchpadValidationError('This is your name: %s' % name)
            elif name in existing_aliases:
                # This is already an alias to this pillar, so there's no need
                # to validate it.
                pass
            else:
                name_field._validate(name)

    def set(self, object, value):
        object.setAliases(self._split_input(value))

    def get(self, object):
        return " ".join(object.aliases)


class ProductBugTracker(Choice):
    """A bug tracker used by a Product.

    It accepts all the values in the vocabulary, as well as a special
    marker object, which represents the Malone bug tracker.
    This field uses two attributes on the Product to model its state:
    'official_malone' and 'bugtracker'
    """
    implements(IReferenceChoice)
    malone_marker = object()

    @property
    def schema(self):
        # The IBugTracker needs to be imported here to avoid an import loop.
        from lp.bugs.interfaces.bugtracker import IBugTracker
        return IBugTracker

    def get(self, ob):
        if ob.official_malone:
            return self.malone_marker
        else:
            return getattr(ob, self.__name__)

    def set(self, ob, value):
        if self.readonly:
            raise TypeError("Can't set values on read-only fields.")
        if value is self.malone_marker:
            ob.official_malone = True
            setattr(ob, self.__name__, None)
        else:
            ob.official_malone = False
            setattr(ob, self.__name__, value)


class URIField(TextLine):
    implements(IURIField)

    def __init__(self, allowed_schemes=(), allow_userinfo=True,
                 allow_port=True, allow_query=True, allow_fragment=True,
                 trailing_slash=None, **kwargs):
        super(URIField, self).__init__(**kwargs)
        self.allowed_schemes = set(allowed_schemes)
        self.allow_userinfo = allow_userinfo
        self.allow_port = allow_port
        self.allow_query = allow_query
        self.allow_fragment = allow_fragment
        self.trailing_slash = trailing_slash

    def set(self, object, value):
        """Canonicalize a URL and set it as a field value."""
        value = self.normalize(value)
        super(URIField, self).set(object, value)

    def normalize(self, input):
        """See `IURIField`."""
        if input is None:
            return input

        try:
            uri = URI(input)
        except InvalidURIError as exc:
            raise LaunchpadValidationError(str(exc))
        # If there is a policy for whether trailing slashes are
        # allowed at the end of the path segment, ensure that the
        # URI conforms.
        if self.trailing_slash is not None:
            if self.trailing_slash:
                uri = uri.ensureSlash()
            else:
                uri = uri.ensureNoSlash()
        input = unicode(uri)
        return input

    def _validate(self, value):
        """Ensure the value is a valid URI."""

        uri = URI(self.normalize(value))

        if self.allowed_schemes and uri.scheme not in self.allowed_schemes:
            raise LaunchpadValidationError(
                'The URI scheme "%s" is not allowed.  Only URIs with '
                'the following schemes may be used: %s'
                % (uri.scheme, ', '.join(sorted(self.allowed_schemes))))

        if not self.allow_userinfo and uri.userinfo is not None:
            raise LaunchpadValidationError(
                'A username may not be specified in the URI.')

        if not self.allow_port and uri.port is not None:
            raise LaunchpadValidationError(
                'Non-default ports are not allowed.')

        if not self.allow_query and uri.query is not None:
            raise LaunchpadValidationError(
                'URIs with query strings are not allowed.')

        if not self.allow_fragment and uri.fragment is not None:
            raise LaunchpadValidationError(
                'URIs with fragment identifiers are not allowed.')

        super(URIField, self)._validate(value)


class FieldNotBoundError(Exception):
    """The field is not bound to any object."""


class BaseImageUpload(Bytes):
    """Base class for ImageUpload fields.

    Any subclass of this one must be used in conjunction with
    ImageUploadWidget and must define the following attributes:
    - dimensions: the exact dimensions of the image; a tuple of the
      form (width, height).
    - max_size: the maximum size of the image, in bytes.
    """

    implements(IBaseImageUpload)

    exact_dimensions = True
    dimensions = ()
    max_size = 0

    def __init__(self, default_image_resource=None, **kw):
        # 'default_image_resource' is a keyword argument so that the
        # class constructor can be used in the same way as other
        # Interface attribute specifiers.
        if default_image_resource is None:
            raise AssertionError(
                "You must specify a default image resource.")

        self.default_image_resource = default_image_resource
        Bytes.__init__(self, **kw)

    def getCurrentImage(self):
        if self.context is None:
            raise FieldNotBoundError("This field must be bound to an object.")
        else:
            try:
                current = getattr(self.context, self.__name__)
            except ForbiddenAttribute:
                # When this field is used in add forms it gets bound to
                # I*Set objects, which don't have the attribute represented
                # by the field, so we need this hack here.
                current = None
            return current

    def _valid_image(self, image):
        """Check that the given image is under the given constraints."""
        # No global import to avoid hard dependency on PIL being installed
        import PIL.Image
        if len(image) > self.max_size:
            raise LaunchpadValidationError(_(dedent("""
                This image exceeds the maximum allowed size in bytes.""")))
        try:
            pil_image = PIL.Image.open(StringIO(image))
        except (IOError, ValueError):
            raise LaunchpadValidationError(_(dedent("""
                The file uploaded was not recognized as an image; please
                check it and retry.""")))
        width, height = pil_image.size
        required_width, required_height = self.dimensions
        if self.exact_dimensions:
            if width != required_width or height != required_height:
                raise LaunchpadValidationError(_(dedent("""
                    This image is not exactly ${width}x${height}
                    pixels in size."""),
                    mapping={'width': required_width,
                             'height': required_height}))
        else:
            if width > required_width or height > required_height:
                raise LaunchpadValidationError(_(dedent("""
                    This image is larger than ${width}x${height}
                    pixels in size."""),
                    mapping={'width': required_width,
                             'height': required_height}))
        return True

    def _validate(self, value):
        if hasattr(value, 'seek'):
            value.seek(0)
            content = value.read()
        else:
            content = value
        super(BaseImageUpload, self)._validate(content)
        self._valid_image(content)

    def set(self, object, value):
        if value is not KEEP_SAME_IMAGE:
            Bytes.set(self, object, value)


class IconImageUpload(BaseImageUpload):

    dimensions = (14, 14)
    max_size = 5 * 1024


class LogoImageUpload(BaseImageUpload):

    dimensions = (64, 64)
    max_size = 50 * 1024


class MugshotImageUpload(BaseImageUpload):

    dimensions = (192, 192)
    max_size = 100 * 1024


class LocationField(Field):
    """A Location field."""

    implements(ILocationField)

    @property
    def latitude(self):
        return self.value.latitude

    @property
    def longitude(self):
        return self.value.longitude

    @property
    def time_zone(self):
        return self.value.time_zone


class PillarNameField(BlacklistableContentNameField):
    """Base field used for names of distros/projects/products."""

    errormessage = _("%s is already used by another project")

    def _getByName(self, name):
        return getUtility(IPillarNameSet).getByName(name)


class ProductNameField(PillarNameField):
    """Field used by IProduct.name."""

    @property
    def _content_iface(self):
        # Local import to avoid circular dependencies.
        from lp.registry.interfaces.product import IProduct
        return IProduct


def is_public_person(person):
    """Return True if the person is public."""
    from lp.registry.interfaces.person import IPerson
    if not IPerson.providedBy(person):
        return False
    return person.visibility == PersonVisibility.PUBLIC


def is_public_person_or_closed_team(person):
    """Return True if person is a Person or not an open or delegated team."""
    from lp.registry.interfaces.person import IPerson
    if not IPerson.providedBy(person):
        return False
    if not person.is_team:
        return person.visibility == PersonVisibility.PUBLIC
    return person.membership_policy in EXCLUSIVE_TEAM_POLICY


class PrivateTeamNotAllowed(ConstraintNotSatisfied):
    __doc__ = _("A private team is not allowed.")


class PrivateMembershipTeamNotAllowed(ConstraintNotSatisfied):
    __doc__ = _("A private-membership team is not allowed.")


class IPersonChoice(IReferenceChoice):
    """A marker for a choice among people."""


class PersonChoice(Choice):
    """A person or team.

    This is useful as a superclass and provides a clearer error message than
    "Constraint not satisfied".
    """
    implements(IPersonChoice)
    schema = IObject    # Will be set to IPerson once IPerson is defined.


class PublicPersonChoice(PersonChoice):
    """A person or team who is public."""

    def constraint(self, value):
        if is_public_person(value):
            return True
        else:
            # The vocabulary prevents the revealing of private team names.
            raise PrivateTeamNotAllowed(value)


class WorkItemsText(Text):

    def parseLine(self, line):
        workitem_match = WORKITEM_RE.search(line)
        if workitem_match:
            assignee = workitem_match.group('assignee')
            title = workitem_match.group('title')
            status = workitem_match.group('status')
        else:
            raise LaunchpadValidationError(
                'Invalid work item format: "%s"' % line)
        if title == '':
            raise LaunchpadValidationError(
                'No work item title found on "%s"' % line)
        if title.startswith('['):
            raise LaunchpadValidationError(
                'Missing closing "]" for assignee on "%s".' % line)

        return {'title': title, 'status': status.strip().upper(),
                'assignee': assignee}

    def parse(self, text):
        sequence = 0
        milestone = None
        work_items = []
        if text is not None:
            for line in text.splitlines():
                if line.strip() == '':
                    continue
                milestone_match = MILESTONE_RE.search(line)
                if milestone_match:
                    milestone_part = milestone_match.group(1).strip()
                    if milestone_part == '':
                        milestone = None
                    else:
                        milestone = milestone_part.split()[-1]
                else:
                    new_work_item = self.parseLine(line)
                    new_work_item['milestone'] = milestone
                    new_work_item['sequence'] = sequence
                    sequence += 1
                    work_items.append(new_work_item)
        return work_items

    def validate(self, value):
        self.parseAndValidate(value)

    def parseAndValidate(self, text):
        work_items = self.parse(text)
        for work_item in work_items:
            work_item['status'] = self.getStatus(work_item['status'])
            work_item['assignee'] = self.getAssignee(work_item['assignee'])
            work_item['milestone'] = self.getMilestone(work_item['milestone'])
        return work_items

    def getStatus(self, text):
        valid_statuses = SpecificationWorkItemStatus.items
        if text.lower() not in [item.name.lower() for item in valid_statuses]:
            raise LaunchpadValidationError('Unknown status: %s' % text)
        return valid_statuses[text.upper()]

    def getAssignee(self, assignee_name):
        if assignee_name is None:
            return None
        from lp.registry.interfaces.person import IPersonSet
        assignee = getUtility(IPersonSet).getByName(assignee_name)
        if assignee is None:
            raise LaunchpadValidationError(
                "Unknown person name: %s" % assignee_name)
        return assignee

    def getMilestone(self, milestone_name):
        if milestone_name is None:
            return None

        target = self.context.target

        milestone = None
        from lp.registry.interfaces.distribution import IDistribution
        from lp.registry.interfaces.milestone import IMilestoneSet
        from lp.registry.interfaces.product import IProduct
        if IProduct.providedBy(target):
            milestone = getUtility(IMilestoneSet).getByNameAndProduct(
                milestone_name, target)
        elif IDistribution.providedBy(target):
            milestone = getUtility(IMilestoneSet).getByNameAndDistribution(
                milestone_name, target)
        else:
            raise AssertionError("Unexpected target type.")

        if milestone is None:
            raise LaunchpadValidationError("The milestone '%s' is not valid "
                                           "for the target '%s'." % \
                                               (milestone_name, target.name))
        return milestone
