# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Adapters to figure out affiliations between people and pillars/bugs etc.

When using a person in a given context, for example as a selection item in a
picker used to choose a bug task assignee, it is important to provide an
indication as to how that person may be affiliated with the context. Amongst
other reasons, this provides a visual cue that the correct person is being
selected for example.

The adapters herein are provided for various contexts so that for a given
person, the relevant affiliation details may be determined.

"""

__metaclass__ = type

__all__ = [
    'IHasAffiliation',
    ]

from collections import namedtuple

from zope.component import adapter
from zope.interface import (
    implements,
    Interface,
    )

from lp.answers.interfaces.questionsperson import IQuestionsPerson
from lp.app.interfaces.launchpad import IHasIcon
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.distributionsourcepackage import (
    IDistributionSourcePackage,
    )
from lp.registry.model.teammembership import find_team_participations


class IHasAffiliation(Interface):
    """The affiliation status of a person with a context."""

    def getAffiliationBadges(persons):
        """Return the badges for the type of affiliation each person has.

        The return value is a list of namedtuples:
        BadgeDetails(url, label, role)

        If a person has no affiliation with this object, their entry is None.
        """

BadgeDetails = namedtuple('BadgeDetails', ('url', 'label', 'role'))


@adapter(Interface)
class PillarAffiliation(object):
    """Default affiliation adapter.

    Subclasses may need to override getPillars() in order to provide the
    pillar entities for which affiliation is to be determined. A given context
    may supply for than one pillar for which affiliation can be determined.
    The default is just to use the context object directly.
    """

    implements(IHasAffiliation)

    # We rank the affiliations from most important to least important.
    # Unlisted roles are given a rank of 10.
    affiliation_priorities = {
        'maintainer': 1,
        'driver': 2,
        'bug supervisor': 3,
    }

    def __init__(self, context):
        self.context = context

    def getPillars(self):
        return [self.context]

    def getIconUrl(self, pillar):
        if (IHasIcon.providedBy(self.context)
                    and self.context.icon is not None):
            icon_url = self.context.icon.getURL()
            return icon_url
        if IHasIcon.providedBy(pillar) and pillar.icon is not None:
            icon_url = pillar.icon.getURL()
            return icon_url
        if IDistribution.providedBy(pillar):
            return "/@@/distribution-badge"
        else:
            return "/@@/product-badge"

    def _getAffiliation(self, person, pillars):
        """ Return the affiliation information for a person, if any.

        Subclasses will override this method to perform specific affiliation
        checks.
        The return result is a list of AffiliationRecord.
        """
        return []

    def _getAffiliationTeamRoles(self, pillars):
        """ Return teams for which a person needs to belong, if affiliated.

        A person is affiliated with a pillar if they are in the list of
        drivers or are the maintainer.
        """
        result = {}
        for pillar in pillars:
            result[BadgeDetails(
                self.getIconUrl(pillar),
                pillar.displayname, 'maintainer')] = [pillar.owner]
            result[BadgeDetails(
                self.getIconUrl(pillar),
                pillar.displayname, 'driver')] = pillar.drivers
        return result

    def getAffiliationBadges(self, persons):
        """ Return the affiliation badge details for people given a context.

        There are 2 ways we check for affiliation:
        1. Generic membership checks of particular teams as returned by
           _getAffiliationTeamRoles
        2. Specific affiliation checks as performed by _getAffiliation
        """
        pillars = self.getPillars()
        result = []

        # We find the teams to check for participation..
        affiliation_team_details = self._getAffiliationTeamRoles(pillars)
        teams_to_check = set()
        for teams in affiliation_team_details.values():
            teams_to_check.update(teams)
        # We gather the participation for the persons.
        people_teams = find_team_participations(persons, teams_to_check)

        for person in persons:
            # Specific affiliations
            badges = self._getAffiliation(person, pillars)
            # Generic, team based affiliations
            affiliated_teams = people_teams.get(person, [])
            for affiliated_team in affiliated_teams:
                for badge, teams in affiliation_team_details.items():
                    if affiliated_team in teams:
                        badges.append(badge)

            if not badges:
                result.append([])
                continue

            # Sort the affiliation list according to the importance of each
            # affiliation role.
            badges.sort(
                key=lambda badge:
                    self.affiliation_priorities.get(badge.role, 10))
            result.append(badges)
        return result


class BugTaskPillarAffiliation(PillarAffiliation):
    """An affiliation adapter for bug tasks."""
    def getPillars(self):
        result = []
        bug = self.context.bug
        for bugtask in bug.bugtasks:
            result.append(bugtask.pillar)
        return result

    def _getAffiliationTeamRoles(self, pillars):
        """ A person is affiliated with a bugtask based on (in order):
        - owner of bugtask pillar
        - driver of bugtask pillar
        - bug supervisor of bugtask pillar
        """
        super_instance = super(BugTaskPillarAffiliation, self)
        result = super_instance._getAffiliationTeamRoles(pillars)
        for pillar in pillars:
            result[BadgeDetails(
                self.getIconUrl(pillar),
                pillar.displayname,
                'bug supervisor')] = [pillar.bug_supervisor]
        return result


class BranchPillarAffiliation(BugTaskPillarAffiliation):
    """An affiliation adapter for branches."""

    def getPillars(self):
        pillar = self.context.product or self.context.distribution
        if pillar is None:
            # This is a +junk branch.
            return []
        return [pillar]

    def getBranch(self):
        return self.context

    def _getAffiliation(self, person, pillars):
        super_instance = super(BranchPillarAffiliation, self)
        result = super_instance._getAffiliation(person, pillars)
        for pillar in pillars:
            if self.getBranch().isPersonTrustedReviewer(person):
                result.append(BadgeDetails(
                    self.getIconUrl(pillar),
                    pillar.displayname, 'trusted reviewer'))
        return result


class CodeReviewVotePillarAffiliation(BranchPillarAffiliation):
    """An affiliation adapter for CodeReviewVotes."""

    def getPillars(self):
        """Return the target branch'pillar."""
        branch = self.getBranch()
        return [branch.product or branch.distribution]

    def getBranch(self):
        return self.context.branch_merge_proposal.target_branch


class DistroSeriesPillarAffiliation(PillarAffiliation):
    """An affiliation adapter for distroseries."""
    def getPillars(self):
        return [self.context.distribution]


class ProductSeriesPillarAffiliation(PillarAffiliation):
    """An affiliation adapter for productseries."""
    def getPillars(self):
        return [self.context.product]


class SpecificationPillarAffiliation(PillarAffiliation):
    """An affiliation adapter for blueprints."""
    def getPillars(self):
        return [self.context.target]


class QuestionPillarAffiliation(PillarAffiliation):
    """An affiliation adapter for questions.

    A person is affiliated with a question based on (in order):
    - answer contact for question target
    - owner of question target
    - driver of question target
    """

    def getPillars(self):
        return [self.context.product or self.context.distribution]

    def _getAffiliation(self, person, pillars):
        super_instance = super(QuestionPillarAffiliation, self)
        result = super_instance._getAffiliation(person, pillars)
        target = self.context.target
        if IDistributionSourcePackage.providedBy(target):
            question_targets = (target, target.distribution)
        else:
            question_targets = (target, )
        questions_person = IQuestionsPerson(person)
        for target in questions_person.getDirectAnswerQuestionTargets():
            if target in question_targets:
                result.append(
                    BadgeDetails(
                        self.getIconUrl(pillars[0]),
                        target.displayname, 'answer contact'))
        for target in questions_person.getTeamAnswerQuestionTargets():
            if target in question_targets:
                result.append(
                    BadgeDetails(
                        self.getIconUrl(pillars[0]),
                        target.displayname, 'answer contact'))
        return result
