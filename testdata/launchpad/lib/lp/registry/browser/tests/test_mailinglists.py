
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test harness for mailinglist views unit tests."""

__metaclass__ = type

import transaction
from zope.component import getUtility

from lp.app.browser.tales import PersonFormatterAPI
from lp.registry.interfaces.person import PersonVisibility
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.authorization import check_permission
from lp.testing import (
    login_person,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import (
    DatabaseFunctionalLayer,
    LaunchpadFunctionalLayer,
    )
from lp.testing.pages import (
    extract_text,
    find_tag_by_id,
    )
from lp.testing.views import (
    create_initialized_view,
    create_view,
    )


class MailingListTestCase(TestCaseWithFactory):
    """Verify the content in +mailing-list-portlet."""

    def makeTeamWithMailingList(self, name=None, owner=None, visibility=None):
        if owner is None:
            owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            name=name, owner=owner, visibility=visibility)
        login_person(owner)
        self.factory.makeMailingList(team=team, owner=owner)
        return team

    def makeHeldMessage(self, team, sender=None):
        # Requires LaunchpadFunctionalLayer.
        if sender is None:
            sender = self.factory.makePerson(
                email='him@eg.dom', name='him', displayname='Him')
        raw = '\n'.join([
            'From: Him <him@eg.dom>',
            'To: %s' % str(team.mailing_list.address),
            'Subject: monkey',
            'Message-ID: <monkey>',
            'Date: Fri, 01 Aug 2000 01:09:00 -0000',
            '',
            'First paragraph.\n\nSecond paragraph.\n\nThird paragraph.'
            ])
        message_set = getUtility(IMessageSet)
        message = message_set.fromEmail(raw)
        transaction.commit()
        held_message = team.mailing_list.holdMessage(message)
        return sender, message, held_message


class MailingListSubscriptionControlsTestCase(TestCaseWithFactory):
    """Verify the team index subscribe/unsubscribe to mailing list content."""

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(MailingListSubscriptionControlsTestCase, self).setUp()
        self.a_team = self.factory.makeTeam(name='a')
        self.b_team = self.factory.makeTeam(name='b', owner=self.a_team)
        self.b_team_list = self.factory.makeMailingList(team=self.b_team,
            owner=self.b_team.teamowner)
        self.user = self.factory.makePerson()
        with person_logged_in(self.a_team.teamowner):
            self.a_team.addMember(self.user, self.a_team.teamowner)

    def test_subscribe_control_renders(self):
        login_person(self.user)
        view = create_view(self.b_team, name='+index',
            principal=self.user, server_url='http://launchpad.dev',
            path_info='/~%s' % self.b_team.name)
        content = view.render()
        link_tag = find_tag_by_id(content, "link-list-subscribe")
        self.assertNotEqual(None, link_tag)

    def test_subscribe_control_doesnt_render_for_non_member(self):
        other_person = self.factory.makePerson()
        login_person(other_person)
        view = create_view(self.b_team, name='+index',
            principal=other_person, server_url='http://launchpad.dev',
            path_info='/~%s' % self.b_team.name)
        content = view.render()
        self.assertNotEqual('', content)
        link_tag = find_tag_by_id(content, "link-list-subscribe")
        self.assertEqual(None, link_tag)


class TestMailingListPortlet(MailingListTestCase):
    """Verify the content in +mailing-list-portlet."""

    layer = DatabaseFunctionalLayer

    def test_public_archive(self):
        # Public teams have public archives.
        team = self.makeTeamWithMailingList()
        view = create_view(
            team, name='+portlet-mailinglist',
            server_url='http://launchpad.dev', path_info='/~%s' % team.name)
        link = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('View public archive', extract_text(link))

    def test_private_archive(self):
        # Private teams have private archives.
        team = self.makeTeamWithMailingList(
            visibility=PersonVisibility.PRIVATE)
        view = create_view(
            team, name='+portlet-mailinglist',
            server_url='http://launchpad.dev', path_info='/~%s' % team.name)
        link = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('View private archive', extract_text(link))


class TestTeamMailingListConfigurationView(MailingListTestCase):
    """Verify the +mailinglist view."""

    layer = DatabaseFunctionalLayer

    def test_public_achive_message_with_list(self):
        # Public teams have public archives.
        team = self.makeTeamWithMailingList()
        view = create_initialized_view(
            team, name='+mailinglist', principal=team.teamowner,)
        element = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('public', extract_text(element))

    def test_private_message_message_with_list(self):
        # Private teams have private archives.
        team = self.makeTeamWithMailingList(
            visibility=PersonVisibility.PRIVATE)
        view = create_initialized_view(
            team, name='+mailinglist', principal=team.teamowner)
        element = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('private', extract_text(element))

    def test_public_achive_message_without_list(self):
        # Public teams have public archives.
        team = self.factory.makeTeam()
        view = create_initialized_view(
            team, name='+mailinglist', principal=team.teamowner,)
        element = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('public', extract_text(element))

    def test_private_message_message_without_list(self):
        # Private teams have private archives.
        owner = self.factory.makePerson()
        team = self.factory.makeTeam(
            owner=owner, visibility=PersonVisibility.PRIVATE)
        login_person(owner)
        view = create_initialized_view(
            team, name='+mailinglist', principal=owner)
        element = find_tag_by_id(view(), 'mailing-list-archive')
        self.assertEqual('private', extract_text(element))


class HeldMessageViewTestCase(MailingListTestCase):
    """Verify the +moderation view."""

    layer = LaunchpadFunctionalLayer

    def test_view_properties(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        view = create_initialized_view(
            held_message, name='+moderation')
        self.assertEqual(message.subject, view.subject)
        self.assertEqual(message.rfc822msgid, view.message_id)
        self.assertEqual(message.datecreated, view.date)
        self.assertEqual(PersonFormatterAPI(sender).link(None), view.author)
        self.assertEqual("First paragraph.", view.body_summary)
        self.assertEqual(
            "\n<p>\nSecond paragraph.\n</p>\n\n<p>\nThird paragraph.\n</p>\n",
            view.body_details)

    def test_view_append_paragraph(self):
        # Consecutive lines are wrapped in html <p> tags.
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        view = create_initialized_view(
            held_message, name='+moderation')
        paragraphs = []
        view._append_paragraph(paragraphs, ['line 1', 'line 2'])
        self.assertEqual(
            ['\n<p>\n', 'line 1\nline 2', '\n</p>\n'], paragraphs)
        paragraphs = []
        view._append_paragraph(paragraphs, [])
        self.assertEqual([], paragraphs)

    def test_render(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        view = create_initialized_view(
            held_message, name='+moderation', principal=team.teamowner)
        markup = view.render()
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*Subject:.*monkey.*From:.*Him.*Date:.*2000-08-01.*Message-ID'
            '.*&lt;monkey&gt;.*class="foldable-quoted".*',
            markup)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*<input type="radio" value="approve"'
            '.*name="field.%3Cmonkey%3E" />'
            '.*<input type="radio" value="reject"'
            '.*name="field.%3Cmonkey%3E" />'
            '.*<input type="radio" value="discard"'
            '.*name="field.%3Cmonkey%3E" />'
            '.*<input type="radio" value="hold"'
            '.* name="field.%3Cmonkey%3E" checked="checked" />.*',
            markup)


class TeamMailingListModerationViewTestCase(MailingListTestCase):
    """Verify the +mailinglist-moderate view."""

    layer = LaunchpadFunctionalLayer

    def test_permissions(self):
        # Team admins and privileged users can see the view others cannot.
        team = self.makeTeamWithMailingList()
        member = self.factory.makePerson()
        with person_logged_in(team.teamowner):
            team.addMember(member, team.teamowner)
            view = create_initialized_view(team, name='+mailinglist-moderate')
            self.assertIs(True, check_permission('launchpad.Edit', view))
        with person_logged_in(member):
            self.assertIs(False, check_permission('launchpad.Edit', view))

    def test_message_summary_text(self):
        team = self.makeTeamWithMailingList()
        # No messages.
        view = create_initialized_view(
            team, name='+mailinglist-moderate', principal=team.teamowner)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*There are no mailing list messages requiring your review.*',
            view.render())
        # One message.
        self.makeHeldMessage(team)
        view = create_initialized_view(
            team, name='+mailinglist-moderate', principal=team.teamowner)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*1.*message has.*been posted to your mailing list.*',
            view.render())

    def test_batching(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        for i in range(5):
            self.makeHeldMessage(team, sender)
        view = create_initialized_view(
            team, name='+mailinglist-moderate', principal=team.teamowner)
        self.assertEqual(6, view.hold_count)
        self.assertEqual('messages', view.held_messages.heading)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*upper-batch-nav-batchnav-next.*lower-batch-nav-batchnav-next.*',
            view.render())

    def test_widgets(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        view = create_initialized_view(
            team, name='+mailinglist-moderate', principal=team.teamowner)
        self.assertTextMatchesExpressionIgnoreWhitespace(
            '.*name="field.%3Cmonkey%3E.*', view.render())

    def test_approve(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        form = {
            'field.%3Cmonkey%3E': 'approve',
            'field.actions.moderate': 'Moderate',
            }
        view = create_initialized_view(
            team, name='+mailinglist-moderate', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(
            'Held message approved; Message-ID: &lt;monkey&gt;',
             view.request.notifications[0].message)

    def test_discard(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        form = {
            'field.%3Cmonkey%3E': 'discard',
            'field.actions.moderate': 'Moderate',
            }
        view = create_initialized_view(
            team, name='+mailinglist-moderate', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(
            'Held message discarded; Message-ID: &lt;monkey&gt;',
             view.request.notifications[0].message)

    def test_reject(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        form = {
            'field.%3Cmonkey%3E': 'reject',
            'field.actions.moderate': 'Moderate',
            }
        view = create_initialized_view(
            team, name='+mailinglist-moderate', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(
            'Held message rejected; Message-ID: &lt;monkey&gt;',
             view.request.notifications[0].message)

    def test_held(self):
        team = self.makeTeamWithMailingList()
        sender, message, held_message = self.makeHeldMessage(team)
        form = {
            'field.%3Cmonkey%3E': 'hold',
            'field.actions.moderate': 'Moderate',
            }
        view = create_initialized_view(
            team, name='+mailinglist-moderate', form=form)
        self.assertEqual([], view.errors)
        self.assertEqual(
            'Messages still held for review: 1 of 1',
             view.request.notifications[0].message)
