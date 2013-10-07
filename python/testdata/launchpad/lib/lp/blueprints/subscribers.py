# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type


from lp.blueprints.enums import SpecificationGoalStatus
from lp.registry.interfaces.person import IPerson
from lp.services.database.sqlbase import block_implicit_flushes


def specification_update_lifecycle_status(spec, event):
    """Mark the specification as started and/or complete if appropriate.

    Does nothing if there is no user associated with the event.
    """
    if event.user is None:
        return
    spec.updateLifecycleStatus(IPerson(event.user))


@block_implicit_flushes
def spec_created(spec, event):
    """Assign karma to the user who created the spec."""
    IPerson(event.user).assignKarma(
        'addspec', product=spec.product, distribution=spec.distribution)


@block_implicit_flushes
def spec_modified(spec, event):
    """Check changes made to the spec and assign karma if needed."""
    user = IPerson(event.user)
    spec_delta = event.object.getDelta(event.object_before_modification, user)
    if spec_delta is None:
        return

    # easy 1-1 mappings from attribute changing to karma
    attrs_actionnames = {
        'title': 'spectitlechanged',
        'summary': 'specsummarychanged',
        'specurl': 'specurlchanged',
        'priority': 'specpriority',
        'productseries': 'specseries',
        'distroseries': 'specseries',
        'milestone': 'specmilestone',
        }

    for attr, actionname in attrs_actionnames.items():
        if getattr(spec_delta, attr, None) is not None:
            user.assignKarma(
                actionname, product=spec.product,
                distribution=spec.distribution)


@block_implicit_flushes
def spec_branch_created(spec_branch, event):
    """Assign karma to the user who linked the spec to the branch."""
    spec_branch.branch.target.assignKarma(
        spec_branch.registrant, 'specbranchcreated')
