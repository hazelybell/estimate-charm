# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interfaces including and related to IDiff."""

__metaclass__ = type

__all__ = [
    'IDiff',
    'IIncrementalDiff',
    'IPreviewDiff',
    ]

from lazr.restful.declarations import (
    export_as_webservice_entry,
    exported,
    )
from lazr.restful.fields import Reference
from zope.interface import Interface
from zope.schema import (
    Bool,
    Bytes,
    Datetime,
    Dict,
    Int,
    Text,
    TextLine,
    )

from lp import _
from lp.code.interfaces.revision import IRevision


class IDiff(Interface):
    """A diff that is stored in the Library."""

    text = Text(
        title=_('Textual contents of a diff.'), readonly=True,
        description=_("The text may be cut off at a defined maximum size."))

    oversized = Bool(
        readonly=True,
        description=_(
            "True if the size of the content is over the defined maximum "
            "size."))

    diff_text = exported(
        Bytes(title=_('Content of this diff'), required=True, readonly=True))

    diff_lines_count = exported(
        Int(title=_('The number of lines in this diff.'), readonly=True))

    diffstat = exported(
        Dict(title=_('Statistics about this diff'), readonly=True))

    added_lines_count = exported(
        Int(title=_('The number of lines added in this diff.'),
            readonly=True))

    removed_lines_count = exported(
        Int(title=_('The number of lines removed in this diff.'),
            readonly=True))


class IIncrementalDiff(Interface):
    """An incremental diff for a merge proposal."""

    diff = Reference(IDiff, title=_('The Diff object.'), readonly=True)

    # The schema for the Reference gets patched in _schema_circular_imports.
    branch_merge_proposal = Reference(
        Interface, readonly=True,
        title=_('The branch merge proposal that diff relates to.'))

    old_revision = Reference(
        IRevision, readonly=True, title=_('The old revision of the diff.'))

    new_revision = Reference(
        IRevision, readonly=True, title=_('The new revision of the diff.'))


class IPreviewDiff(IDiff):
    """A diff generated to show actual diff between two branches.

    This diff will be used primarily for branch merge proposals where we are
    trying to determine the effective changes of landing the source branch on
    the target branch.
    """
    export_as_webservice_entry(publish_web_link=False)

    source_revision_id = exported(
        TextLine(
            title=_('The tip revision id of the source branch used to '
                    'generate the diff.'),
            readonly=True))

    target_revision_id = exported(
        TextLine(
            title=_('The tip revision id of the target branch used to '
                    'generate the diff.'),
            readonly=True))

    prerequisite_revision_id = exported(
        TextLine(
            title=_('The tip revision id of the prerequisite branch used to '
                    'generate the diff.'),
            readonly=True))

    conflicts = exported(
        Text(title=_(
                'The conflicts text describing any path or text conflicts.'),
             readonly=True))

    has_conflicts = Bool(
        title=_('Has conflicts'), readonly=True,
        description=_('The previewed merge produces conflicts.'))

    branch_merge_proposal_id = Int(
        title=_('The branch merge proposal for this diff.'), readonly=True)

    # The schema for the Reference gets patched in _schema_circular_imports.
    branch_merge_proposal = exported(
        Reference(
            Interface, readonly=True,
            title=_('The branch merge proposal that diff relates to.')))

    date_created = Datetime(
        title=_("When this diff was created."), readonly=True)

    stale = exported(
        Bool(readonly=True, description=_(
                'If the preview diff is stale, it is out of date when '
                'compared to the tip revisions of the source, target, and '
                'possibly prerequisite branches.')))

    def getFileByName(filename):
        """Return the file under +files with specified name."""
