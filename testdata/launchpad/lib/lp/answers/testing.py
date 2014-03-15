# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper functions for Answer Tracker tests."""

__metaclass__ = type
__all__ = [
    'QuestionFactory',
    ]

from zope.component import getUtility

from lp.answers.interfaces.questiontarget import IQuestionTarget
from lp.registry.interfaces.pillar import IPillarNameSet
from lp.services.webapp.interfaces import ILaunchBag


class QuestionFactory:
    """Helper object that can be used to quickly create questions."""

    @classmethod
    def _getQuestionTarget(cls, target_name):
        """Return the `IQuestionTarget` to use.

        It returns the pillar with the target_name and makes sure it
        provides `IQuestionTarget`.
        """
        assert isinstance(target_name, basestring), (
            "expected a project name: %r", target_name)
        target = getUtility(IPillarNameSet).getByName(target_name)
        assert target is not None, (
            'No project with name %s' % target_name)
        assert IQuestionTarget.providedBy(target), (
            "%r doesn't provide IQuestionTarget" % target)
        return target

    @classmethod
    def createManyByProject(cls, specification):
        """Create a number of questions on selected projects.

        The function expects a sequence of tuples of the form
        (project_name, question_count).

        project_name should be the name of a pillar providing
        `IQuestionTarget`.

        question_count is the number of questions to create on the target.

        Questions will appear as posted by the currently logged in user.
        """
        for project, question_count in specification:
            target = cls._getQuestionTarget(project)
            cls.createManyByTarget(target, question_count)

    @classmethod
    def createManyByTarget(cls, target, question_count):
        """Create a number of questions on a selected target

        :param question_count: The number of questions to create on the
            target.

        Questions will appear as posted by the currently logged in user.
        """
        owner = getUtility(ILaunchBag).user
        created_questions = []
        for index in range(question_count):
            replacements = {'index': index, 'target': target.displayname}
            created_questions.append(target.newQuestion(
                owner,
                'Question %(index)s on %(target)s' % replacements,
                'Description %(index)s on %(target)s' % replacements))
        return created_questions
