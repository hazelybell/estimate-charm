/* Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Team add member animations and ui.
 *
 * @module lp.registry.team
 */

YUI.add('lp.registry.team', function(Y) {

var module = Y.namespace('lp.registry.team');

/*
 * Initialize click handler for the add member link
 *
 * @method setup_add_member_handler
 */
module.setup_add_member_handler = function(step_title) {
    var config = {
        header: 'Add a member',
        step_title: step_title,
        picker_activator: '.menu-link-add_member',
        picker_type: 'person'
    };

    config.save = _add_member;
    Y.lp.app.picker.create('ValidTeamMember', config);
};

var _add_member = function(selected_person) {
    var box = Y.one('#membership');
    var spinner = box.one('#add-member-spinner');
    var addmember_link = box.one('.menu-link-add_member');
    addmember_link.addClass('hidden');
    spinner.removeClass('hidden');
    var disable_spinner = function() {
        addmember_link.removeClass('hidden');
        spinner.addClass('hidden');
    };
    lp_client = new Y.lp.client.Launchpad();

    var error_handler = new Y.lp.client.ErrorHandler();
    error_handler.clearProgressUI = disable_spinner;
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(addmember_link, error_msg);
    };

    addmember_config = {
        on: {
            success: function(change_and_status) {
                var did_status_change = change_and_status[0];
                var current_status = change_and_status[1];
                var members_section, members_ul, count_elem;
                if (did_status_change === false) {
                    disable_spinner();
                    Y.lp.app.errors.display_info(
                        selected_person.title + ' is already ' +
                        current_status.toLowerCase() +
                        ' as a member of the team.');
                    return;
                }

                if (current_status === 'Invited') {
                    members_section = box.one('#recently-invited');
                    members_ul = box.one('#recently-invited-ul');
                    count_elem = box.one('#invited-member-count');
                } else if (current_status === 'Proposed') {
                    members_section = box.one('#recently-proposed');
                    members_ul = box.one('#recently-proposed-ul');
                    count_elem = box.one('#proposed-member-count');
                } else if (current_status === 'Approved') {
                    members_section = box.one('#recently-approved');
                    members_ul = box.one('#recently-approved-ul');
                    count_elem = box.one('#approved-member-count');
                } else {
                    Y.lp.app.errors.display_error(
                        addmember_link,
                        'Unexpected status: ' + current_status);
                    return;
                }
                var first_node = members_ul.get('firstChild');

                var xhtml_person_handler = function(person_html) {
                    if (count_elem === null && current_status === 'Invited') {
                        count_elem = Y.Node.create(
                            '<strong id="invited-member-count">' +
                            '1</strong>');
                        var count_box = Y.one(
                            '#membership #membership-counts');
                        count_box.append(Y.Node.create(
                            '<span>, </span>'));
                        count_box.append(count_elem);
                        count_box.append(Y.Node.create(
                            '<span> <a href="+members#invited">' +
                            'invited members</a></span>'));
                    } else {
                        var count = count_elem.get('innerHTML');
                        count = parseInt(count, 10) + 1;
                        count_elem.set('innerHTML', count);
                    }
                    person_repr = Y.Node.create(
                        '<li>' + person_html + '</li>');
                    members_section.removeClass('hidden');
                    members_ul.insertBefore(person_repr, first_node);
                    anim = Y.lp.anim.green_flash({node: person_repr});
                    anim.run();
                    disable_spinner();
                };

                xhtml_person_config = {
                    on: {
                        success: xhtml_person_handler,
                        failure: error_handler.getFailureHandler()
                    },
                    accept: Y.lp.client.XHTML
                };
                lp_client.get(selected_person.api_uri, xhtml_person_config);
            },
            failure: error_handler.getFailureHandler()
        },
        parameters: {
            // XXX: EdwinGrubbs 2009-12-16 bug=497602
            // Why do I always have to get absolute URIs out of the URIs
            // in the picker's result/client.links?
            reviewer: Y.lp.client.get_absolute_uri(LP.links.me),
            person: Y.lp.client.get_absolute_uri(selected_person.api_uri)
        }
    };

    lp_client.named_post(
        LP.cache.context.self_link, 'addMember', addmember_config);
};

/**
 * Update the widget's membership policy extra help message according to the
 * team's, visibility. If PRIVATE, display a fixed message explaining the
 * membership policy must be private. If PUBLIC, display whatever message
 * was previously displayed (if any).
 * @param widget
 * @param visibility
 */
module.show_membership_policy_extra_help = function(widget, visibility) {
    var extra_help_widget = widget.ancestor('div').one('.info');

    // The current extra help text as displayed.
    var current_extra_help = null;
    if (Y.Lang.isObject(extra_help_widget)) {
        current_extra_help = extra_help_widget.get('text');
    }
    // The previously saved extra help text from when the team was public.
    var saved_extra_help = widget.getData('public_extra_help');

    var extra_help = 'Private teams must have a restricted ' +
        'membership policy.';
    if (visibility === 'PRIVATE') {
        // Save the last public extra help text.
        if (Y.Lang.isValue(current_extra_help)) {
            widget.setData('public_extra_help', current_extra_help);
        }
    } else {
        extra_help = saved_extra_help;
    }
    // extra_help contains the text to display. If none, destroy the extra
    // help widget.
    if (Y.Lang.isValue(extra_help)) {
        //Create the extra help widget if necessary.
        if (!Y.Lang.isObject(extra_help_widget)) {
            extra_help_widget = Y.Node.create('<div></div>')
                .addClass('sprite')
                .addClass('info');
            widget.insert(extra_help_widget, 'before');
        }
        extra_help_widget.set('text', extra_help);
    } else {
        if (Y.Lang.isObject(extra_help_widget)) {
            extra_help_widget.remove(true);
        }
    }
};

/**
 * The team's visibility has changed so we need to show or hide subscription
 * policy choices as appropriate.
 * @param visibility
 */
module.visibility_changed_subscription = function(visibility) {
    var widget_label = Y.one("[for='field.membership_policy']");
    if (!Y.Lang.isValue(widget_label)) {
        return;
    }
    var widget = widget_label.ancestor('div').one('.radio-button-widget');
    widget.all("td input[name='field.membership_policy']")
            .each(function(choice_node) {
        var input_row = choice_node.ancestor('tr');
        var help_row = input_row.next(function (node) {
            return node.one('.formHelp') !== null;
        });
        var policy_value = choice_node.get('value');
        // PRIVATE teams can only have RESTRICTED membership policy.
        if (visibility === 'PRIVATE') {
            if (policy_value === 'RESTRICTED') {
                choice_node.set('checked', 'checked');
            } else {
                choice_node.set('checked', '');
                input_row.addClass('hidden');
                help_row.addClass('hidden');
            }
        } else {
            input_row.removeClass('hidden');
            help_row.removeClass('hidden');
        }
    });
    module.show_membership_policy_extra_help(widget, visibility);
};


/**
 * Show the extra help about private teams.
 * @param visibility
 */
module.visibility_changed_visibility = function(visibility) {
    var widget_label = Y.one("[for='field.visibility']");
    if (!Y.Lang.isValue(widget_label)) {
        return;
    }
    var extra_help_node = Y.one('#visibility-extra-help');
    if (!extra_help_node) {
        // Create the needed extra help node once.
        extra_help_node = Y.Node.create(
            '<div id="visibility-extra-help"></div>')
            .addClass('sprite')
            .addClass('info')
            .addClass('hidden')
            .set('text', 'Private teams cannot become public later.');
        widget_label.ancestor('div').one('.formHelp').insert(
            extra_help_node, 'before');
    }
    if (visibility === 'PRIVATE') {
        extra_help_node.removeClass('hidden');
    } else {
        extra_help_node.addClass('hidden');
    }
};

/**
 * The team's visibility has changed so we need to update the form and
 * explain the consequences.
 * @param visibility
 */
module.visibility_changed = function(visibility) {
    module.visibility_changed_subscription(visibility);
    module.visibility_changed_visibility(visibility);
};

/**
 * Setup javascript for team adding/editing.
 */
module.initialise_team_edit = function() {
    // If no visibility widget, then bale.
    var visibility_widget = Y.one("[name='field.visibility']");
    if (!Y.Lang.isValue(visibility_widget)) {
        return;
    }
    var visibility = visibility_widget.get('value');
    module.visibility_changed(visibility);
    visibility_widget.on('change', function(e) {
        module.visibility_changed(visibility_widget.get('value'));
    });
};

}, '0.1', {requires: ['node',
                      'lp.anim',
                      'lp.app.errors',
                      'lp.app.picker',
                      'lp.client',
                      'lp.client.plugins'
                      ]});
