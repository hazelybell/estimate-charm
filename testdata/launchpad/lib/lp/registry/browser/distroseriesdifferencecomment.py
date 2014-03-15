# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View and helper for `DistroSeriesDifferenceComment`."""

__metaclass__ = type

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.services.webapp import LaunchpadView


class DistroSeriesDifferenceCommentView(LaunchpadView):
    """View class for `DistroSeriesDifferenceComment`.

    :ivar is_error: Whether the comment is an error message from Launchpad.
        Package copy failures are stored as `DistroSeriesDifferenceComments`,
        but rendered to be visually recognizable as errors.
    """

    def __init__(self, *args, **kwargs):
        super(DistroSeriesDifferenceCommentView, self).__init__(
            *args, **kwargs)
        error_persona = getUtility(ILaunchpadCelebrities).janitor
        self.is_error = (self.context.comment_author == error_persona)
