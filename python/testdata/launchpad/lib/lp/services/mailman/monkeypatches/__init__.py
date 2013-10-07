# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Install Launchpad integration code into the Mailman module."""

import os
import shutil

from lazr.config import as_host_port


def monkey_patch(mailman_path, config):
    """Monkey-patch an installed Mailman 2.1 tree.

    Rather than maintain a forked tree of Mailman 2.1, we apply a set of
    changes to an installed Mailman tree.  This tree can be found rooted at
    mailman_path.

    This should usually mean just copying a file from this directory into
    mailman_path.  Rather than build a lot of process into the mix, just hard
    code each transformation here.
    """
    # Hook Mailman to Launchpad by writing a custom mm_cfg.py file which adds
    # the top of our Launchpad tree to Mailman's sys.path.  The mm_cfg.py file
    # won't do much more than set up sys.path and do an from-import-* to get
    # everything that doesn't need to be dynamically calculated at run-time.
    # Things that can only be calculated at run-time are written to mm_cfg.py
    # now.  It's okay to simply overwrite any existing mm_cfg.py, since we'll
    # provide everything Mailman needs.
    #
    # Remember, don't rely on Launchpad's config object in the mm_cfg.py file
    # or in the lp.services.mailman.monkeypatches.defaults module because
    # Mailman will not be able to initialize Launchpad's configuration system.
    # Instead, anything that's needed from config should be written to the
    # mm_cfg.py file now.
    #
    # Calculate the parent directory of the lp module.  This directory
    # will get appended to Mailman's sys.path.
    import lp
    from lp.services.mailman.config import configure_siteowner
    launchpad_top = os.path.abspath(
        os.path.join(os.path.dirname(lp.__file__), os.pardir, os.pardir))
    # Read the email footer template for all Launchpad messages.
    from lp.services.mail.helpers import get_email_template
    footer = get_email_template(
        'mailinglist-footer.txt', app='services/mailman/monkeypatches')
    # Write the mm_cfg.py file, filling in the dynamic values now.
    host, port = as_host_port(config.mailman.smtp)
    owner_address, owner_password = configure_siteowner(
        config.mailman.build_site_list_owner)
    config_path_in = os.path.join(os.path.dirname(__file__), 'mm_cfg.py.in')
    config_file_in = open(config_path_in)
    try:
        config_template = config_file_in.read()
    finally:
        config_file_in.close()
    config_path_out = os.path.join(mailman_path, 'Mailman', 'mm_cfg.py')
    config_file_out = open(config_path_out, 'w')
    try:
        print >> config_file_out, config_template % dict(
            launchpad_top=launchpad_top,
            smtp_host=host,
            smtp_port=port,
            smtp_max_rcpts=config.mailman.smtp_max_rcpts,
            smtp_max_sesions_per_connection=(
                config.mailman.smtp_max_sesions_per_connection),
            xmlrpc_url=config.mailman.xmlrpc_url,
            xmlrpc_sleeptime=config.mailman.xmlrpc_runner_sleep,
            xmlrpc_timeout=config.mailman.xmlrpc_timeout,
            xmlrpc_subscription_batch_size=(
                config.mailman.subscription_batch_size),
            site_list_owner=owner_address,
            list_help_header=config.mailman.list_help_header,
            list_subscription_headers=(
                config.mailman.list_subscription_headers),
            archive_url_template=config.mailman.archive_url_template,
            list_owner_header_template=(
                config.mailman.list_owner_header_template),
            footer=footer,
            var_dir=config.mailman.build_var_dir,
            shared_secret=config.mailman.shared_secret,
            soft_max_size=config.mailman.soft_max_size,
            hard_max_size=config.mailman.hard_max_size,
            register_bounces_every=config.mailman.register_bounces_every,
            )
    finally:
        config_file_out.close()
    # Mailman's qrunner system requires runner modules to live in the
    # Mailman.Queue package.  Set things up so that there's a hook module in
    # there for the XMLRPCRunner.
    runner_path = os.path.join(mailman_path,
                               'Mailman', 'Queue', 'XMLRPCRunner.py')
    runner_file = open(runner_path, 'w')
    try:
        print >> runner_file, (
            'from lp.services.mailman.monkeypatches.xmlrpcrunner '
            'import *')
    finally:
        runner_file.close()
    # Install our handler wrapper modules so that Mailman can find them.  Most
    # of the actual code of the handler comes from our monkey patches modules.
    for mm_name, lp_name in (('LaunchpadMember', 'lphandler'),
                             ('LaunchpadHeaders', 'lpheaders'),
                             ('LPStanding', 'lpstanding'),
                             ('LPModerate', 'lpmoderate'),
                             ('LPSize', 'lpsize'),
                             ):
        handler_path = os.path.join(
            mailman_path, 'Mailman', 'Handlers', mm_name + '.py')
        handler_file = open(handler_path, 'w')
        try:
            package = 'lp.services.mailman.monkeypatches'
            module = package + '.' + lp_name
            print >> handler_file, 'from', module, 'import *'
        finally:
            handler_file.close()

    here = os.path.dirname(__file__)
    # Install the MHonArc control file.
    mhonarc_rc_file = os.path.join(here, 'lp-mhonarc-common.mrc')
    runtime_data_dir = os.path.join(config.mailman.build_var_dir, 'data')
    shutil.copy(mhonarc_rc_file, runtime_data_dir)
    # Install the launchpad site templates.
    launchpad_template_path = os.path.join(here, 'sitetemplates')
    site_template_path = os.path.join(mailman_path, 'templates', 'site')
    if os.path.isdir(site_template_path):
        shutil.rmtree(site_template_path)
    shutil.copytree(launchpad_template_path, site_template_path)
