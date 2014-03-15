# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Module docstring goes here."""

__metaclass__ = type

import datetime
from StringIO import StringIO
import time

from zope.component import getUtility
from zope.interface import Interface
from zope.schema.interfaces import TooShort

from lp.app.validators import LaunchpadValidationError
from lp.blueprints.enums import SpecificationWorkItemStatus
from lp.registry.enums import (
    EXCLUSIVE_TEAM_POLICY,
    INCLUSIVE_TEAM_POLICY,
    )
from lp.registry.interfaces.nameblacklist import INameBlacklistSet
from lp.services.database.interfaces import IStore
from lp.services.fields import (
    BaseImageUpload,
    BlacklistableContentNameField,
    FormattableDate,
    is_public_person_or_closed_team,
    StrippableText,
    WorkItemsText,
    )
from lp.testing import (
    login_person,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


def make_target():
    """Make a trivial object to be a target of the field setting."""

    class Simple:
        """A simple class to test setting fields on."""

    return Simple()


class TestFormattableDate(TestCase):

    def test_validation_fails_on_bad_data(self):
        field = FormattableDate()
        date_value = datetime.date(
            *(time.strptime('1000-01-01', '%Y-%m-%d'))[:3])
        self.assertRaises(
            LaunchpadValidationError, field.validate, date_value)

    def test_validation_passes_good_data(self):
        field = FormattableDate()
        date_value = datetime.date(
            *(time.strptime('2010-01-01', '%Y-%m-%d'))[:3])
        self.assertIs(None, field.validate(date_value))


class TestStrippableText(TestCase):

    def test_strips_text(self):
        # The set method should strip the string before setting the field.
        target = make_target()
        field = StrippableText(__name__='test', strip_text=True)
        self.assertTrue(field.strip_text)
        field.set(target, '  testing  ')
        self.assertEqual('testing', target.test)

    def test_strips_text_trailing_only(self):
        # The set method strips the trailing whitespace.
        target = make_target()
        field = StrippableText(
            __name__='test', strip_text=True, trailing_only=True)
        self.assertTrue(field.trailing_only)
        field.set(target, '  testing  ')
        self.assertEqual('  testing', target.test)

    def test_default_constructor(self):
        # If strip_text is not set, or set to false, then the text is not
        # stripped when set.
        target = make_target()
        field = StrippableText(__name__='test')
        self.assertFalse(field.strip_text)
        field.set(target, '  testing  ')
        self.assertEqual('  testing  ', target.test)

    def test_setting_with_none(self):
        # The set method is given None, the attribute is set to None
        target = make_target()
        field = StrippableText(__name__='test', strip_text=True)
        field.set(target, None)
        self.assertIs(None, target.test)

    def test_validate_min_contraints(self):
        # The minimum length constraint tests the stripped string.
        field = StrippableText(
            __name__='test', strip_text=True, min_length=1)
        self.assertRaises(TooShort, field.validate, u'  ')

    def test_validate_max_contraints(self):
        # The minimum length constraint tests the stripped string.
        field = StrippableText(
            __name__='test', strip_text=True, max_length=2)
        self.assertEqual(None, field.validate(u'  a  '))


class TestWorkItemsTextValidation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestWorkItemsTextValidation, self).setUp()
        self.field = WorkItemsText(__name__='test')

    def test_parseandvalidate(self):
        status = SpecificationWorkItemStatus.TODO
        assignee = self.factory.makePerson()
        milestone = self.factory.makeMilestone()
        title = 'A work item'
        specification = self.factory.makeSpecification(
            product=milestone.product)
        field = self.field.bind(specification)
        work_items_text = (
            "Work items for %s:\n"
           "[%s]%s: %s" % (milestone.name, assignee.name, title, status.name))
        work_item = field.parseAndValidate(work_items_text)[0]
        self.assertEqual({'assignee': assignee,
                          'milestone': milestone,
                          'sequence': 0,
                          'status': status,
                          'title': title}, work_item)

    def test_unknown_assignee_is_rejected(self):
        person_name = 'test-person'
        self.assertRaises(
            LaunchpadValidationError, self.field.getAssignee, person_name)

    def test_validate_valid_assignee(self):
        assignee = self.factory.makePerson()
        self.assertEqual(assignee, self.field.getAssignee(assignee.name))

    def test_validate_unset_assignee(self):
        self.assertIs(None, self.field.getAssignee(None))

    def test_validate_unset_milestone(self):
        self.assertIs(None, self.field.getMilestone(None))

    def test_validate_unknown_milestone(self):
        specification = self.factory.makeSpecification()
        field = self.field.bind(specification)
        self.assertRaises(
            LaunchpadValidationError, field.getMilestone, 'does-not-exist')

    def test_validate_valid_product_milestone(self):
        milestone = self.factory.makeMilestone()
        specification = self.factory.makeSpecification(
            product=milestone.product)
        field = self.field.bind(specification)
        self.assertEqual(milestone, field.getMilestone(milestone.name))

    def test_validate_valid_distro_milestone(self):
        distro = self.factory.makeDistribution()
        milestone = self.factory.makeMilestone(distribution=distro)
        specification = self.factory.makeSpecification(
            distribution=milestone.distribution)
        field = self.field.bind(specification)
        self.assertEqual(milestone, field.getMilestone(milestone.name))

    def test_validate_invalid_milestone(self):
        milestone_name = 'test-milestone'
        self.factory.makeMilestone(name=milestone_name)
        # Milestone exists but is not a target for this spec.
        specification = self.factory.makeSpecification(product=None)
        field = self.field.bind(specification)
        self.assertRaises(
            LaunchpadValidationError, field.getMilestone, milestone_name)

    def test_validate_invalid_status(self):
        self.assertRaises(
            LaunchpadValidationError, self.field.getStatus,
            'Invalid status: FOO')

    def test_validate_valid_statuses(self):
        statuses = [SpecificationWorkItemStatus.TODO,
                    SpecificationWorkItemStatus.DONE,
                    SpecificationWorkItemStatus.POSTPONED,
                    SpecificationWorkItemStatus.INPROGRESS,
                    SpecificationWorkItemStatus.BLOCKED]
        for status in statuses:
            validated_status = self.field.getStatus(status.name)
            self.assertEqual(validated_status, status)


class TestWorkItemsText(TestCase):

    def setUp(self):
        super(TestWorkItemsText, self).setUp()
        self.field = WorkItemsText(__name__='test')

    def test_validate_raises_LaunchpadValidationError(self):
        self.assertRaises(
            LaunchpadValidationError, self.field.validate,
            'This is not a valid work item.')

    def test_single_line_parsing(self):
        work_items_title = 'Test this work item'
        parsed = self.field.parseLine('%s: TODO' % (work_items_title))
        self.assertEqual(parsed['title'], work_items_title)
        self.assertEqual(parsed['status'], 'TODO')

    def test_url_and_colon_in_title(self):
        work_items_title = 'Test this: which is a url: http://www.linaro.org/'
        parsed = self.field.parseLine('%s: TODO' % (work_items_title))
        self.assertEqual(parsed['title'], work_items_title)

    def test_silly_caps_status_parsing(self):
        parsed_upper = self.field.parseLine('Test this work item: TODO    ')
        self.assertEqual(parsed_upper['status'], 'TODO')
        parsed_lower = self.field.parseLine('Test this work item:     todo')
        self.assertEqual(parsed_lower['status'], 'TODO')
        parsed_camel = self.field.parseLine('Test this work item: ToDo')
        self.assertEqual(parsed_camel['status'], 'TODO')

    def test_parseLine_without_status_fails(self):
        # We should require an explicit status to avoid the problem of work
        # items with a url but no status.
        self.assertRaises(
            LaunchpadValidationError, self.field.parseLine,
            'Missing status')

    def test_parseLine_without_title_fails(self):
        self.assertRaises(
            LaunchpadValidationError, self.field.parseLine,
            ':TODO')

    def test_parseLine_without_title_with_assignee_fails(self):
        self.assertRaises(
            LaunchpadValidationError, self.field.parseLine,
            '[test-person] :TODO')

    def test_assignee_and_bracket(self):
        title = "Work item with one ] bracket"
        work_items_text = ("Work items:\n"
                           "[person] %s: TODO" % title)
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed, [{'title': title,
                      'status': 'TODO',
                      'assignee': 'person',
                      'milestone': None,
                      'sequence': 0}])

    def test_assignee_and_brackets(self):
        title = "Work item with two [2] brackets"
        work_items_text = ("Work items:\n"
                           "[person] %s: TODO" % title)
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed, [{'title': title,
                      'status': 'TODO',
                      'assignee': 'person',
                      'milestone': None,
                      'sequence': 0}])

    def test_no_assignee_and_brackets(self):
        title = "Work item with [] brackets"
        work_items_text = ("Work items:\n"
                           "%s: TODO" % title)
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed, [{'title': title,
                      'status': 'TODO',
                      'assignee': None,
                      'milestone': None,
                      'sequence': 0}])

    def test_parse_none(self):
        # When empty text box is submitted, None is being passed in instead.
        work_items_text = None
        parsed = self.field.parse(work_items_text)
        self.assertEqual([], parsed)

    def test_multi_line_parsing(self):
        title_1 = 'Work item 1'
        title_2 = 'Work item 2'
        work_items_text = "Work items:\n%s: TODO\n%s: POSTPONED" % (title_1,
                                                                  title_2)
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed, [{'title': title_1,
                      'status': 'TODO',
                      'assignee': None, 'milestone': None, 'sequence': 0},
                     {'title': title_2,
                      'status': 'POSTPONED',
                      'assignee': None, 'milestone': None, 'sequence': 1}])

    def test_multi_line_parsing_different_milestones(self):
        title_1 = 'Work item 1'
        title_2 = 'Work item 2'
        work_items_text = ("Work items:\n%s: TODO\nWork items for test-ms:\n"
                           "%s: POSTPONED" % (title_1, title_2))
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed,
            [{'title': title_1,
              'status': 'TODO',
              'assignee': None, 'milestone': None, 'sequence': 0},
             {'title': title_2,
              'status': 'POSTPONED',
              'assignee': None, 'milestone': 'test-ms', 'sequence': 1}])

    def test_multi_line_parsing_different_milestones_reversed(self):
        title_1 = 'Work item 1'
        title_2 = 'Work item 2'
        work_items_text = ("Work items for test-ms:\n%s: TODO\nWork items:\n"
                           "%s: POSTPONED" % (title_1, title_2))
        parsed = self.field.parse(work_items_text)
        self.assertEqual(
            parsed, [{'title': title_1,
                      'status': 'TODO',
                      'assignee': None, 'milestone': 'test-ms', 'sequence': 0},
                     {'title': title_2,
                      'status': 'POSTPONED',
                      'assignee': None, 'milestone': None, 'sequence': 1}])

    def test_parse_assignee(self):
        title = 'Work item 1'
        assignee = 'test-person'
        work_items_text = "[%s]%s: TODO" % (assignee, title)
        parsed = self.field.parseLine(work_items_text)
        self.assertEqual(parsed['assignee'], assignee)

    def test_parse_assignee_with_space(self):
        title = 'Work item 1'
        assignee = 'test-person'
        work_items_text = "[%s] %s: TODO" % (assignee, title)
        parsed = self.field.parseLine(work_items_text)
        self.assertEqual(parsed['assignee'], assignee)

    def test_parseLine_with_missing_closing_bracket_for_assignee(self):
        self.assertRaises(
            LaunchpadValidationError, self.field.parseLine,
            "[test-person A single work item: TODO")

    def test_parse_empty_lines_have_no_meaning(self):
        parsed = self.field.parse("\n\n\n\n\n\n\n\n")
        self.assertEqual(parsed, [])

    def test_parse_status(self):
        work_items_text = "A single work item: TODO"
        parsed = self.field.parse(work_items_text)
        self.assertEqual(parsed[0]['status'], 'TODO')

    def test_parse_milestone(self):
        milestone = '2012.02'
        title = "Work item for a milestone"
        work_items_text = "Work items for %s:\n%s: TODO" % (milestone, title)
        parsed = self.field.parse(work_items_text)
        self.assertEqual(parsed,
            [{'title': title,
              'status': 'TODO',
              'assignee': None, 'milestone': milestone, 'sequence': 0}])

    def test_parse_multi_milestones(self):
        milestone_1 = '2012.02'
        milestone_2 = '2012.03'
        title_1 = "Work item for a milestone"
        title_2 = "Work item for a later milestone"
        work_items_text = ("Work items for %s:\n%s: POSTPONED\n\nWork items "
                           "for %s:\n%s: TODO" % (milestone_1, title_1,
                                                  milestone_2, title_2))
        parsed = self.field.parse(work_items_text)
        self.assertEqual(parsed,
                         [{'title': title_1,
                           'status': 'POSTPONED',
                           'assignee': None, 'milestone': milestone_1,
                           'sequence': 0},
                          {'title': title_2,
                           'status': 'TODO',
                           'assignee': None, 'milestone': milestone_2,
                           'sequence': 1}])

    def test_parse_orphaned_work_items(self):
        # Work items not in a milestone block belong to the latest specified
        # milestone.
        milestone_1 = '2012.02'
        milestone_2 = '2012.03'
        title_1 = "Work item for a milestone"
        title_2 = "Work item for a later milestone"
        title_3 = "A work item preceeded by a blank line"
        work_items_text = (
            "Work items for %s:\n%s: POSTPONED\n\nWork items for %s:\n%s: "
            "TODO\n\n%s: TODO" % (milestone_1, title_1, milestone_2, title_2,
                                  title_3))
        parsed = self.field.parse(work_items_text)
        self.assertEqual(parsed,
                         [{'title': title_1,
                           'status': 'POSTPONED',
                           'assignee': None, 'milestone': milestone_1,
                           'sequence': 0},
                          {'title': title_2,
                           'status': 'TODO',
                           'assignee': None, 'milestone': milestone_2,
                           'sequence': 1},
                          {'title': title_3,
                           'status': 'TODO',
                           'assignee': None, 'milestone': milestone_2,
                           'sequence': 2}])

    def test_sequence_single_workitem(self):
        parsed = self.field.parse("A single work item: TODO")
        self.assertEqual(0, parsed[0]['sequence'])

    def test_only_workitems_get_sequence(self):
        parsed = self.field.parse("A single work item: TODO\n"
                             "A second work item: TODO\n"
                             "\n"
                             "Work items for 2012.02:\n"
                             "Work item for a milestone: TODO\n")
        self.assertEqual([(wi['title'], wi['sequence']) for wi in parsed],
                         [("A single work item", 0), ("A second work item", 1),
                          ("Work item for a milestone", 2)])


class TestBlacklistableContentNameField(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestBlacklistableContentNameField, self).setUp()
        name_blacklist_set = getUtility(INameBlacklistSet)
        self.team = self.factory.makeTeam()
        admin_exp = name_blacklist_set.create(u'fnord', admin=self.team)
        IStore(admin_exp).flush()

    def makeTestField(self):
        """Return testible subclass."""

        class ITestInterface(Interface):
            pass

        class TestField(BlacklistableContentNameField):
            _content_iface = ITestInterface

            def _getByName(self, name):
                return None

        return TestField(__name__='test')

    def test_validate_fails_with_blacklisted_name_anonymous(self):
        # Anonymous users, processes, cannot create a name that matches
        # a blacklisted name.
        field = self.makeTestField()
        date_value = u'fnord'
        self.assertRaises(
            LaunchpadValidationError, field.validate, date_value)

    def test_validate_fails_with_blacklisted_name_not_admin(self):
        # Users who do not adminster a blacklisted name cannot create
        # a matching name.
        field = self.makeTestField()
        date_value = u'fnord'
        login_person(self.factory.makePerson())
        self.assertRaises(
            LaunchpadValidationError, field.validate, date_value)

    def test_validate_passes_for_admin(self):
        # Users in the team that adminsters a blacklisted name may create
        # matching names.
        field = self.makeTestField()
        date_value = u'fnord'
        login_person(self.team.teamowner)
        self.assertEqual(None, field.validate(date_value))


class TestBaseImageUpload(TestCase):
    """Test for the BaseImageUpload field."""

    class ExampleImageUpload(BaseImageUpload):
        dimensions = (192, 192)
        max_size = 100 * 1024

    def test_validation_corrupt_image(self):
        # ValueErrors raised by PIL become LaunchpadValidationErrors.
        field = self.ExampleImageUpload(default_image_resource='dummy')
        image = StringIO(
            '/* XPM */\n'
            'static char *pixmap[] = {\n'
            '"32 32 253 2",\n'
            '  "00 c #01CAA3",\n'
            '  ".. s None c None",\n'
            '};')
        image.filename = 'foo.xpm'
        self.assertRaises(
            LaunchpadValidationError, field.validate, image)

    def test_validation_non_image(self):
        # IOError raised by PIL become LaunchpadValidationErrors.
        field = self.ExampleImageUpload(default_image_resource='dummy')
        image = StringIO('foo bar bz')
        image.filename = 'foo.jpg'
        self.assertRaises(
            LaunchpadValidationError, field.validate, image)


class Test_is_person_or_closed_team(TestCaseWithFactory):
    """ Tests for is_person_or_closed_team()."""

    layer = DatabaseFunctionalLayer

    def test_non_person(self):
        self.assertFalse(is_public_person_or_closed_team(0))

    def test_person(self):
        person = self.factory.makePerson()
        self.assertTrue(is_public_person_or_closed_team(person))

    def test_open_team(self):
        for policy in INCLUSIVE_TEAM_POLICY:
            open_team = self.factory.makeTeam(membership_policy=policy)
            self.assertFalse(
                is_public_person_or_closed_team(open_team),
                "%s is not open" % policy)

    def test_closed_team(self):
        for policy in EXCLUSIVE_TEAM_POLICY:
            closed_team = self.factory.makeTeam(membership_policy=policy)
            self.assertTrue(
                is_public_person_or_closed_team(closed_team),
                "%s is not closed" % policy)
