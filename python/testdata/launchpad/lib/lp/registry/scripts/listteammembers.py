# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""List all team members: name, preferred email address."""

__metaclass__ = type
__all__ = ['process_team']

import re

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.ssh import SSHKeyType


OUTPUT_TEMPLATES = {
    'simple': '%(name)s, %(email)s',
    'email': '%(email)s',
    'full': '%(teamname)s|%(id)s|%(name)s|%(email)s|'
            '%(displayname)s|%(ubuntite)s',
    'sshkeys': '%(name)s: %(sshkey)s',
    }


class NoSuchTeamError(Exception):
    """Used if non-existent team name is specified."""


bad_ssh_pattern = re.compile('[\r\n\f]')


def make_sshkey_params(member, type_name, key):
    sshkey = "%s %s %s" % (
        type_name,
        bad_ssh_pattern.sub('', key.keytext),
        bad_ssh_pattern.sub('', key.comment).strip())
    return dict(name=member.name, sshkey=sshkey)


def process_team(teamname, display_option='simple'):
    output = []
    people = getUtility(IPersonSet)
    memberset = people.getByName(teamname)
    if memberset == None:
        raise NoSuchTeamError

    template = OUTPUT_TEMPLATES[display_option]
    for member in memberset.allmembers:
        # Email
        if member.preferredemail is not None:
            email = member.preferredemail.email
        else:
            email = '--none--'
        if display_option == 'email':
            for validatedemail in member.validatedemails:
                params = dict(
                    email=validatedemail.email,
                    )
                output.append(template % params)
        # SSH Keys
        sshkey = '--none--'
        if display_option == 'sshkeys':
            for key in member.sshkeys:
                if key.keytype == SSHKeyType.DSA:
                    type_name = 'ssh-dss'
                elif key.keytype == SSHKeyType.RSA:
                    type_name = 'ssh-rsa'
                else:
                    type_name = 'Unknown key type'
                params = make_sshkey_params(member, type_name, key)
                output.append(template % params)
        # Ubuntite
        ubuntite = "no"
        if member.signedcocs:
            for i in member.signedcocs:
                if i.active:
                    ubuntite = "yes"
                    break
        params = dict(
            email=email,
            name=member.name,
            teamname=teamname,
            id=member.id,
            displayname=member.displayname.encode("ascii", "replace"),
            ubuntite=ubuntite,
            sshkey=sshkey,
            )
        output.append(template % params)
    # If we're only looking at email, remove --none-- entries
    # as we're only interested in emails
    if display_option == 'email':
        output = [line for line in output if line != '--none--']
    # If we're only looking at sshkeys, remove --none-- entries
    # as we're only interested in sshkeys
    if display_option == 'sshkeys':
        output = [line for line in output if line[-8:] != '--none--']
    return sorted(output)
