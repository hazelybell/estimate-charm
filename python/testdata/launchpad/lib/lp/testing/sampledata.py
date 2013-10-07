# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Constants that refer to values in sampledata.

If ever you use a literal in a test that refers to sample data, even if it's
just a small number, then you should define it as a constant here.
"""

__metaclass__ = type
__all__ = [
    'ADMIN_EMAIL',
    'BOB_THE_BUILDER_NAME',
    'BUILDD_ADMIN_USERNAME',
    'I386_ARCHITECTURE_NAME',
    'LAUNCHPAD_ADMIN',
    'NO_PRIVILEGE_EMAIL',
    'UBUNTU_DISTRIBUTION_NAME',
    'UBUNTU_UPLOAD_TEAM_NAME',
    'USER_EMAIL',
    ]

# Please use names that reveal intent, rather than being purely
# descriptive, i.e. USER16_NAME isn't as good as
# UBUNTU_DEVELOPER_NAME. Where intent is tricky to convey in the
# name, please leave a comment as well.

# A user with Launchpad Admin privileges.
ADMIN_EMAIL = 'foo.bar@canonical.com'

# A user with buildd admin rights and upload rights to Ubuntu.
BUILDD_ADMIN_USERNAME = 'cprov'
# A couple of builders.
BOB_THE_BUILDER_NAME = 'bob'
I386_ARCHITECTURE_NAME = 'i386'
LAUNCHPAD_ADMIN = 'admin@canonical.com'

NO_PRIVILEGE_EMAIL = 'no-priv@canonical.com'
USER_EMAIL = 'test@canonical.com'
VCS_IMPORTS_MEMBER_EMAIL = 'david.allouche@canonical.com'
# A user that is an admin of ubuntu-team, which has upload rights
# to Ubuntu.
UBUNTU_DISTRIBUTION_NAME = 'ubuntu'
# A team that has upload rights to Ubuntu
UBUNTU_UPLOAD_TEAM_NAME = 'ubuntu-team'
