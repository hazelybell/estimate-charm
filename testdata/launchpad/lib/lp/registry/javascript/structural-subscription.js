/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Form overlay widgets and subscriber handling for structural subscriptions.
 *
 * @module registry
 * @submodule structural_subscription
 */

YUI.add('lp.registry.structural_subscription', function(Y) {

var namespace = Y.namespace('lp.registry.structural_subscription');

var INCLUDE_COMMENTS = 'include-comments',
    FILTER_WRAPPER = 'filter-wrapper',
    ACCORDION_WRAPPER = 'accordion-wrapper',
    ADDED_OR_CLOSED = 'added-or-closed',
    ADDED_OR_CHANGED = 'added-or-changed',
    ADVANCED_FILTER = 'advanced-filter',
    MATCH_ALL = 'match-all',
    MATCH_ANY = 'match-any',
    MUTE_ICON_CLASS = 'mute',
    UNMUTE_ICON_CLASS = 'unmute'
    ;

var cancel_button_html =
    '<button type="button" name="field.actions.cancel" >Cancel</button>';

namespace.lp_client = undefined;

/*
 * An object representing the global actions portlet.
 *
 */
var PortletTarget = function() {};
Y.augment(PortletTarget, Y.Event.Target);
namespace.portlet = new PortletTarget();


/*
 * There can be only one instance of bug_tag_completer because it is watching
 * keyboard input.
 */
namespace.bug_tag_completer = null;


/**
 * This helper function is used to cleanly close down the overlay.
 */
function clean_up() {
    namespace._add_subscription_overlay.hide();
    var filter_wrapper = Y.one('#' + FILTER_WRAPPER);
    filter_wrapper.hide();
    collapse_node(filter_wrapper);
    if (Y.Lang.isObject(namespace.bug_tag_completer)) {
        namespace.bug_tag_completer.destroy();
    }
}

function subscription_success() {
    // TODO Should there be some success notification?
    clean_up();
}

var overlay_error_handler = new Y.lp.client.ErrorHandler();
overlay_error_handler.showError = function(error_msg) {
    namespace._add_subscription_overlay.showError(error_msg);
};
overlay_error_handler.clearProgressUI = function() {
    var submit_button = namespace._add_subscription_overlay.bodyNode.one(
        '[name="field.actions.create"]');
    submit_button.replaceClass('spinner', 'lazr-pos');
};

/**
 * Does the list contain the target?
 *
 * @private
 * @method list_contains
 * @param {List} list The list to search.
 * @param {String} target The target of interest.
 */
function list_contains(list, target) {
    // The list may be undefined in some cases.
    return Y.Lang.isArray(list) && Y.Array.indexOf(list, target) !== -1;
}

// Expose to tests.
namespace._list_contains = list_contains;

/**
 * Reformat the data returned from the add/edit form into something acceptable
 * to send as a PATCH.
 */
function extract_form_data(form_data) {
    if (form_data === 'this is a test') {
        // This is a short-circuit to make testing easier.
        return {};
    }
    var patch_data = {
        description: Y.Lang.trim(form_data.name[0]),
        tags: [],
        find_all_tags: false,
        importances: [],
        statuses: [],
        information_types: []
    };

    // Set the notification level.
    var added_or_closed = list_contains(form_data.events, ADDED_OR_CLOSED);
    var include_comments = list_contains(form_data.filters, INCLUDE_COMMENTS);

    // Chattiness: Lifecycle < Details < Discussion.
    if (added_or_closed) {
        patch_data.bug_notification_level = 'Lifecycle';
    } else if (include_comments) {
        patch_data.bug_notification_level = 'Discussion';
    } else {
        patch_data.bug_notification_level = 'Details';
    }

    // Set the tags, importances, and statuses.  Only do this if
    // ADDED_OR_CHANGED and ADVANCED_FILTER are selected.
    var advanced_filter = (!added_or_closed &&
                           list_contains(form_data.filters, ADVANCED_FILTER));
    if (advanced_filter) {
        // Tags are a list with one element being a space-separated string.
        var tags = form_data.tags[0];
        if (Y.Lang.isValue(tags) && tags !== '') {
            patch_data.tags = Y.Lang.trim(tags).toLowerCase().split(' ');
        }
        patch_data.find_all_tags =
            list_contains(form_data.tag_match, MATCH_ALL);
        if (form_data.importances.length > 0) {
            patch_data.importances = form_data.importances;
        }
        if (form_data.statuses.length > 0) {
            patch_data.statuses = form_data.statuses;
        }
        if (form_data.information_types.length > 0) {
            patch_data.information_types = form_data.information_types;
        }
    } else {
        // clear out the tags, statuses, and importances in case this is an
        // edit.
        patch_data.tags = patch_data.importances = patch_data.statuses = [];
        patch_data.information_types = [];
    }
    return patch_data;
}

// Expose in the namespace for testing purposes.
namespace._extract_form_data = extract_form_data;

/**
 * Given a bug filter, update it with information extracted from a form.
 *
 * @private
 * @method patch_bug_filter
 * @param {Object} bug_filter The bug filter.
 * @param {Object} form_data The data returned from the form submission.
 * @param {Object} on Event handlers to override the defaults.
 */
function patch_bug_filter(bug_filter, form_data, on) {
    var patch_data = extract_form_data(form_data);

    var config = {
        on: Y.merge({
            success: subscription_success,
            failure: overlay_error_handler.getFailureHandler()
            }, on)
        };
    namespace.lp_client.patch(bug_filter.self_link, patch_data, config);
}
namespace.patch_bug_filter = patch_bug_filter;

/**
 * Delete the given filter
 */
function delete_filter(filter) {
    var y_config = {
        method: "POST",
        headers: {'X-HTTP-Method-Override': 'DELETE'},
        on: {failure: overlay_error_handler.getFailureHandler()}
    };
    // This is called with a YUI-proxied version of the filter, so we need
    // to use the YUI getter for the attribute.
    Y.io(filter.get('self_link'), y_config);
}

// Exported for testing.
namespace._delete_filter = delete_filter;

/**
 * Create a new structural subscription filter.
 *
 * @method create_structural_subscription filter
 * @param {Object} who Link to the user or team to be subscribed.
 * @param {Object} form_data The data returned from the form submission.
 * @param {Object} success_callback Function to execute when filter is added.
 */
function add_bug_filter(who, form_data, success_callback) {
    var submit_button = namespace._add_subscription_overlay.bodyNode.one(
        '[name="field.actions.create"]');
    submit_button.replaceClass('lazr-pos', 'spinner');
    var config = {
        on: {success: function (bug_filter) {
                // If we fail to PATCH the new bug filter, DELETE it.
                var on = {
                    failure: function () {
                        // We use the namespace binding so tests can override
                        // these functions.
                        namespace._delete_filter(bug_filter);
                        // Call the failure handler to report the original
                        // error to the user.
                        overlay_error_handler.getFailureHandler()
                            .apply(this, arguments);
                    },
                    success: function (bug_filter) {
                        clean_up();
                        success_callback(form_data, bug_filter);
                        subscription_success(bug_filter);
                        submit_button.replaceClass('spinner', 'lazr-pos');
                    }
                };
                patch_bug_filter(bug_filter.getAttrs(), form_data, on);
            },
            failure: overlay_error_handler.getFailureHandler()
        },
        parameters: {
            subscriber: who
        }
    };

    namespace.lp_client.named_post(LP.cache.context.self_link,
        'addBugSubscriptionFilter', config);
}

// Exported for testing.
namespace._add_bug_filter = add_bug_filter;

/**
 * Create a handler to save the subscription given the form data from a user.
 *
 * @private
 * @method make_add_subscription_handler
 * @param {Object} success_callback Function to execute on successful
 *        addition.
 */
function make_add_subscription_handler(success_callback) {
    var save_subscription = function(form_data) {
        var who;
        var has_errors = check_for_errors_in_overlay(
            namespace._add_subscription_overlay);
        if (has_errors) {
            return;
        }
        if (form_data.recipient[0] === 'user') {
            who = LP.links.me;
        } else {
            // There can be only one.
            who = form_data.team[0];
        }
        return add_bug_filter(who, form_data, success_callback);
    };
    return save_subscription;
}
namespace._make_add_subscription_handler = make_add_subscription_handler;

function check_for_errors_in_overlay(overlay) {
    var has_errors = false;
    var errors = [];
    var field;
    for (field in overlay.field_errors) {
        if (overlay.field_errors.hasOwnProperty(field)) {
            if (overlay.field_errors[field]) {
                has_errors = true;
                errors.push(field);
            }
        }
    }
    if (has_errors) {
        var error_text = errors.pop();
        if (errors.length > 0) {
            error_text = errors.join(', ') + ' and ' + error_text;
        }

        overlay.showError(
            'Value for ' + error_text + ' is invalid.');
        return true;
    } else {
        return false;
    }
}

/**
 * Fill the filter name and description.
 */
function fill_filter_description(filter_node, filter_info, filter) {
    filter_node.one('.filter-description')
        .empty()
        .appendChild(create_filter_description(filter));
    filter_node.one('.filter-name')
        .empty()
        .appendChild(render_filter_title(filter_info, filter));
}

/**
 * Handle the activation of the edit subscription link.
 */
function edit_subscription_handler(context, form_data) {
    var has_errors = check_for_errors_in_overlay(
        namespace._add_subscription_overlay);
    var filter_id = '#filter-description-'+context.filter_id.toString();
    var filter_node = Y.one(
        '#subscription-filter-'+context.filter_id.toString());
    var submit_button = namespace._add_subscription_overlay.bodyNode.one(
        '[name="field.actions.create"]');
    if (has_errors) {
        return;
    }
    var on = {success: function (new_data) {
        submit_button.replaceClass('spinner', 'lazr-pos');
        var description_node = Y.one(filter_id);
        var filter = new_data.getAttrs();
        fill_filter_description(
            filter_node, context.filter_info, filter);
        clean_up();
    }};
    submit_button.replaceClass('lazr-pos', 'spinner');
    patch_bug_filter(context.filter_info.filter, form_data, on);
}

/**
 * Initialize the overlay errors and set up field validators.
 */
function setup_overlay_validators(overlay, overlay_id) {
    overlay.field_errors = {};
    add_input_validator(overlay, overlay_id, 'tags', get_error_for_tags_list);
}

var ellipsis_supported =
    typeof document.createElement('span').style.textOverflow === 'string';
var is_gecko = navigator.product === 'Gecko';
// If we're running on a Gecko-based browser (like Firefox) and it doesn't
// have text-overflow then use the ellipsis hack.  We put it on the namespace
// so tests can manipulate it.
namespace.using_ellipsis_hack = is_gecko && !ellipsis_supported;

/**
 * Populate the overlay element with the contents of the add/edit form.
 */
function create_overlay(content_box_id, overlay_id, submit_button,
                        submit_callback, success_callback) {
    // Some of our code currently expects to create a new overlay every time
    // we render. This is not a performance problem now, and simplifies some
    // of the code.  Therefore, before we create an overlay, we need to make
    // sure that there is not one already.  If there is, destroy it.
    if (Y.Lang.isValue(namespace._add_subscription_overlay)) {
        namespace._add_subscription_overlay.destroy();
    }
    var header = Y.Node.create('<h2/>')
            .set('id', 'subscription-overlay-title')
            .set('text', 'Add a mail subscription '+
                'for '+LP.cache.context.title+' bugs')
            .setStyle('display', 'block')
            .setStyle('overflow', 'hidden')
            .setStyle('textOverflow', 'ellipsis')
            .setStyle('whiteSpace', 'nowrap')
            .setStyle('width', '21em');
    // Create the overlay.
    namespace._add_subscription_overlay = new Y.lp.ui.FormOverlay({
        headerContent: header,
        form_content: Y.one(overlay_id),
        visible: false,
        form_submit_button: submit_button,
        form_cancel_button: Y.Node.create(cancel_button_html),
        form_submit_callback: function(formdata) {
            // Do not clean up if saving was not successful.
            submit_callback(formdata);
        }
    });

    var side_portlets = Y.one('#side-portlets');
    if (side_portlets) {
        namespace._add_subscription_overlay.set('align', {
            node: side_portlets,
            points: [Y.WidgetPositionAlign.TR, Y.WidgetPositionAlign.TL]
        });
    } else {
        namespace._add_subscription_overlay.set('centered', true);
    }
    namespace._add_subscription_overlay.render(content_box_id);
    if (side_portlets) {
        Y.one('#subscription-overlay-title').scrollIntoView();
    }
    if (namespace.using_ellipsis_hack) {
        // Look away.
        var header_text = header.get('text');
        var i;
        for (i=header_text.length; i--; i > 0) {
            if (header.get('scrollWidth') <= header.get('offsetWidth')) {
                if (i !== header_text.length) {
                    header.addClass('force-ellipsis');
                }
                break;
            }
            header.set('text', header_text.substring(0, i));
        }
    }
    setup_overlay_validators(namespace._add_subscription_overlay, overlay_id);
    // Prevent cruft from hanging around upon closing.
    // For some reason, clicking on the cancel button doesn't fire a cancel
    // event, so we have to wire up this event handler.
    namespace._add_subscription_overlay.get('form_cancel_button').on(
        'click', clean_up);
    namespace._add_subscription_overlay.on('submit', clean_up);
    namespace._add_subscription_overlay.on('cancel', clean_up);
    Y.after(
        namespace._add_subscription_overlay._focusChild,
        namespace._add_subscription_overlay, 'show');
}


/**
 * Reset the overlay form to initial values.
 */
function clear_overlay(content_node, no_recipient_picker) {
    content_node = content_node.one('#overlay-container');

    if (no_recipient_picker) {
        set_recipient_label(content_node, undefined);
    } else {
        set_recipient(content_node, false, undefined);
    }
    content_node.one('[name="name"]').set('value', '');
    set_checkboxes(
        content_node, LP.cache.statuses, LP.cache.statuses);
    set_checkboxes(
        content_node, LP.cache.importances, LP.cache.importances);
    set_checkboxes(
        content_node, LP.cache.information_types, LP.cache.information_types);
    content_node.one('[name="tags"]').set('value', '');
    set_radio_buttons(
        content_node, [MATCH_ALL, MATCH_ANY], MATCH_ALL);
    set_radio_buttons(
        content_node, [ADDED_OR_CLOSED, ADDED_OR_CHANGED], ADDED_OR_CLOSED);
    set_checkboxes(
        content_node,
        [INCLUDE_COMMENTS, ADVANCED_FILTER],
        [INCLUDE_COMMENTS]);
    collapse_node(Y.one('#' + ACCORDION_WRAPPER), {duration: 0});
    collapse_node(Y.one('#' + FILTER_WRAPPER), {duration: 0});
}

/**
 * Make a table cell.
 *
 * @private
 * @method make_cell
 * @param {Object} item Item to be placed in the cell.
 * @param {String} name Name of the control.
 */
function make_cell(item, name) {
    var cell = Y.Node.create(
        '<td style="padding-left:3px"><label>' +
        '<input type="checkbox" checked="checked" />' +
        '<span></></label></td>');
    cell.one('span').set('text', item);
    cell.one('input')
        .set('name', name)
        .set('value', item);
    return cell;
}
/**
 * Make a table.
 *
 * @private
 * @method make_table
 * @param {Object} list List of items to be put in the table.
 * @param {String} name Name of the control.
 * @param {Int} num_cols The number of columns for the table to use.
 */
function make_table(list, name, num_cols) {
    var table = Y.Node.create('<table></table>');
    var i, row;
    for (i=0; i<list.length; i++) {
        if (i % num_cols === 0) {
            row = table.appendChild('<tr></tr>');
        }
        row.appendChild(make_cell(list[i], name));
    }
    return table;
}

/**
 * Make selector controls, the links for 'Select all' and
 * 'Select none' that appear within elements with many checkboxes.
 *
 * @private
 * @method make_selector_controls
 * @param {String} parent Name of the parent.
 * @return {Object} Hash with 'all_name', 'none_name', and 'html' keys.
 */
function make_selector_controls(parent) {
    var selectors_id = parent + '-selectors';
    var rv = {};
    rv.all_link = Y.Node.create('<a/>')
        .set('href', '#')
        .set('text', 'Select all')
        .addClass('select-all');
    rv.none_link = Y.Node.create('<a/>')
        .set('href', '#')
        .set('text', 'Select none')
        .addClass('select-none');
    rv.node = Y.Node.create('<div/>')
        .set('id', selectors_id)
        .setStyle('marginBottom', '1ex')
        .setStyle('marginLeft', '1ex')
        .append(rv.all_link)
        .append(Y.Node.create('<span/>')
            .set('text', 'or')
            // Why different margins?  Manual kerning.
            .setStyle('marginLeft', '0.9ex')
            .setStyle('marginRight', '0.7ex'))
        .append(rv.none_link);

    return rv;
}
namespace.make_selector_controls = make_selector_controls;

/**
 * Construct a handler closure for select all/none links.
 */
function make_select_handler(node, all, checked_value) {
    return function(e) {
        e.halt();
        Y.each(all, function(value) {
            get_input_by_value(node, value).set('checked', checked_value);
        });
    };
}

/* We want to call 'resize' directly on tags container
 * when we add a validation failed error message.
 */
var tags_container;

/**
 * Create the accordion.
 *
 * @method create_accordion
 * @param {String} overlay_id Id of the overlay element.
 * @param {Object} content_node Node where the overlay is anchored.
 * @return {Object} accordion The accordion just created.
 */
function create_accordion(overlay_id, content_node) {
    var accordion = new Y.Accordion({
          useAnimation: true,
          collapseOthersOnExpand: true,
          visible: false
    });

    accordion.render(overlay_id);

    var statuses_ai,
        importances_ai,
        tags_ai,
        information_types_ai;

    // Build tags pane.
    tags_ai = new Y.AccordionItem( {
        label: "Tags",
        expanded: false,
        alwaysVisible: false,
        id: "tags_ai",
        contentHeight: {method: "auto"}
    } );
    tags_container = tags_ai;
    tags_ai.set("bodyContent", Y.Node.create('<div><div></div></div>')
        .append(Y.Node.create('<label/>')
            .append(Y.Node.create('<input/>')
                .set('type', 'radio')
                .set('name', 'tag_match')
                .set('checked', 'checked')
                .set('value', MATCH_ALL))
            .append('Match all tags'))
        .append(Y.Node.create('<label/>')
            .append(Y.Node.create('<input/>')
                .set('type', 'radio')
                .set('name', 'tag_match')
                .set('value', MATCH_ANY))
            .append('Match any tags'))
        .append(Y.Node.create('<div/>')
            .append(Y.Node.create('<input/>')
                .set('type', 'text')
                .set('name', 'tags')
                .set('size', '50'))
            .append(Y.Node.create('<a/>')
                .set('target', 'help')
                .set('href', '/+help-bugs/structural-subscription-tags.html')
                .addClass('sprite')
                .addClass('maybe')
                .addClass('action-icon')
                .set('text', 'Structural subscription tags help'))
        .append(Y.Node.create('<div/>')
            .setStyle('paddingBottom', '10px')
            .set('text', 'Separate tags with a space'))));
    accordion.addItem(tags_ai);

    // Build importances pane.
    importances_ai = new Y.AccordionItem( {
        label: "Importances",
        expanded: false,
        alwaysVisible: false,
        id: "importances_ai",
        contentHeight: {method: "auto"}
    } );
    var importances = LP.cache.importances;
    var selectors = make_selector_controls('importances');
    importances_ai.set("bodyContent",
        Y.Node.create('<div id="importances-wrapper"></div>')
            .append(selectors.node)
            .append(make_table(importances, 'importances', 4)));
    accordion.addItem(importances_ai);
    // Wire up the 'all' and 'none' selectors.
    var node = content_node.one('#importances-wrapper');
    selectors.all_link.on('click',
        make_select_handler(node, importances, true));
    selectors.none_link.on('click',
        make_select_handler(node, importances, false));

    // Build statuses pane.
    statuses_ai = new Y.AccordionItem( {
        label: "Statuses",
        expanded: false,
        alwaysVisible: false,
        id: "statuses_ai",
        contentHeight: {method: "auto"}
    } );
    var statuses = LP.cache.statuses;
    selectors = make_selector_controls('statuses');
    statuses_ai.set("bodyContent",
        Y.Node.create('<div id="statuses-wrapper"></div>')
            .append(selectors.node)
            .append(make_table(statuses, 'statuses', 3)));
    accordion.addItem(statuses_ai);
    // Wire up the 'all' and 'none' selectors.
    node = content_node.one('#statuses-wrapper');
    selectors.all_link.on('click',
        make_select_handler(node, statuses, true));
    selectors.none_link.on('click',
        make_select_handler(node, statuses, false));
    var official_bug_tags = LP.cache.context.official_bug_tags || [];
    namespace.bug_tag_completer = Y.lp.bugs.tags_entry.setup_tag_complete(
        'input[name="tags"]', official_bug_tags);

    // Build information_types pane.
    information_types_ai = new Y.AccordionItem( {
        label: "Information types",
        expanded: false,
        alwaysVisible: false,
        id: "information_types_ai",
        contentHeight: {method: "auto"}
    } );
    var information_types = LP.cache.information_types;
    selectors = make_selector_controls('information_types');
    information_types_ai.set("bodyContent",
        Y.Node.create('<div id="information_types-wrapper"></div>')
            .append(selectors.node)
            .append(make_table(information_types, 'information_types', 3)));
    accordion.addItem(information_types_ai);
    // Wire up the 'all' and 'none' selectors.
    node = content_node.one('#information_types-wrapper');
    selectors.all_link.on('click',
        make_select_handler(node, information_types, true));
    selectors.none_link.on('click',
        make_select_handler(node, information_types, false));
    return accordion;
}

/**
 * Collapse the node and set its arrow to 'collapsed'
 */
function collapse_node(node, user_cfg) {
    if (user_cfg && user_cfg.duration === 0) {
        node.setStyles({
            height: 0,
            visibility: 'hidden',
            overflow: 'hidden'
            // Don't set display: none because then the node won't be taken
            // into account and the rendering will sometimes jiggle
            // horizontally when the node is opened.
        });
        node.addClass('lazr-closed').removeClass('lazr-opened');
        return;
    }
    var anim = Y.lp.ui.effects.slide_in(node, user_cfg);
    // XXX: BradCrittenden 2011-03-03 bug=728457 : This fix for
    // resizing needs to be incorporated into lp.ui.effects.  When that
    // is done it should be removed from here.
    anim.on("start", function() {
        node.setStyles({
            visibility: 'visible'
        });
    });
    anim.on("end", function() {
        if (user_cfg && user_cfg.remove_on_end === true) {
            node.remove();
        } else {
            node.setStyles({
                height: 0,
                visibility: 'hidden',
                display: null
                // Don't set display: none because then the node won't be
                // taken into account and the rendering will sometimes jiggle
                // horizontally when the node is opened.
            });
        }
    });
    anim.run();
}

/**
 * Expand the node and set its arrow to 'collapsed'
 */
function expand_node(node, user_cfg) {
    if (user_cfg && user_cfg.duration === 0) {
        node.setStyles({
            height: 'auto',
            visibility: 'visible',
            overflow: null, // Inherit.
            display: null // Inherit.
        });
        node.addClass('lazr-opened').removeClass('lazr-closed');
        return;
    }
    // Set the node to 'hidden' so that the proper size can be found.
    node.setStyles({
        visibility: 'hidden'
    });
    var anim = Y.lp.ui.effects.slide_out(node, user_cfg);
    // XXX: BradCrittenden 2011-03-03 bug=728457 : This fix for
    // resizing needs to be incorporated into lp.ui.effects.  When that
    // is done it should be removed from here.
    anim.on("start", function() {
        // Set the node to 'visible' for the beginning of the animation.
        node.setStyles({
            visibility: 'visible'
        });
    });
    anim.on("end", function() {
        // Change the height to auto when the animation completes.
        node.setStyles({
            height: 'auto'
        });
    });
    anim.run();
}

/**
 * Add a recipient picker to the overlay.
 */
function add_recipient_picker(content_box, hide) {
    var no_recipient_picker = Y.Node.create(
        '<input type="hidden" name="recipient" value="user">' +
        '<span>Yourself</span>');
    var recipient_picker = Y.Node.create(
        '<label><input type="radio" name="recipient" value="user" checked>' +
        '  Yourself</label><br>' +
        '<label><input type="radio" name="recipient" value="team">' +
        '  One of the teams you administer</label><br>' +
        '<dl style="margin-left:25px;">' +
        '  <dt></dt>' +
        '  <dd>' +
        '    <select name="team" id="structural-subscription-teams">' +
        '    </select>' +
        '  </dd>' +
        '</dl>');
    var teams = LP.cache.administratedTeams;
    var node = content_box.one('#bug-mail-recipient');
    node.empty();
    // Populate the team drop down from LP.cache data, if appropriate.
    if (!hide && teams.length > 0) {
        var select = recipient_picker.one('#structural-subscription-teams');
        var i;
        for (i=0; i<teams.length; i++) {
            select.append(Y.Node.create('<option></option>')
                .set('text', teams[i].title)
                .set('value', teams[i].link));
        }
        select.on(
            'change',
            function () {
                Y.one('input[value="team"][name="recipient"]').set(
                    'checked', true);
            }
        );
        node.append(recipient_picker);
    } else {
        node.append(no_recipient_picker);
    }
}

/**
 * Construct the overlay and populate it with the add/edit form.
 */
function setup_overlay(content_box_id, hide_recipient_picker) {
    var content_node = Y.one(content_box_id);
    if (!Y.Lang.isValue(content_node)) {
        Y.error("Node not found: " + content_box_id);
    } else {
        var container_node = content_node.one('#overlay-container');
        if (Y.Lang.isValue(container_node)) {
            container_node.remove();
            container_node.destroy();
        }
    }
    var container = Y.Node.create(
        '<div id="overlay-container"><dl>' +
        '    <dt>Bug mail recipient</dt>' +
        '    <dd id="bug-mail-recipient">' +
        '    </dd>' +
        '  <dt>Subscription name</dt>' +
        '  <dd>' +
        '    <input type="text" name="name">' +
        '    <a target="help" class="sprite maybe action-icon"' +
        '       href="/+help-bugs/structural-subscription-name.html"' +
        '       >Structural subscription</a> ' +
        '  </dd>' +
        '  <dt>Receive mail for bugs affecting' +
        '    <span id="structural-subscription-context-title"></span> '+
        '    that</dt>' +
        '  <dd>' +
        '    <div id="events">' +
        '      <input type="radio" name="events"' +
        '          value="added-or-closed"' +
        '          id="added-or-closed" checked>' +
        '      <label for="added-or-closed">are added or ' +
        '        closed</label>' +
        '      <br>' +
        '      <input type="radio" name="events"' +
        '          value="added-or-changed"' +
        '          id="added-or-changed">' +
        '      <label for="added-or-changed">are added or changed in' +
        '        any way' +
        '        <em id="added-or-changed-more">(more options...)</em>' +
        '      </label>' +
        '    </div>' +
        '    <div id="filter-wrapper" class="ss-collapsible">' +
        '    <dl style="margin-left:25px;">' +
        '      <dt></dt>' +
        '      <dd>' +
        '        <input type="checkbox" name="filters"' +
        '            value="include-comments"' +
        '            id="include-comments">' +
        '        <label for="include-comments">Send mail about' +
        '          comments</label><br>' +
        '        <input type="checkbox" name="filters"' +
        '            value="advanced-filter"' +
        '            id="advanced-filter">' +
        '        <label for="advanced-filter">Bugs must match this' +
        '          filter <em id="advanced-filter-more">(...)</em>' +
        '        </label><br>' +
        '        <div id="accordion-wrapper" ' +
        '            class="ss-collapsible">' +
        '            <dl>' +
        '                <dt></dt>' +
        '                <dd style="margin-left:25px;">' +
        '                    <div id="accordion-overlay"' +
        '                      style="position:relative; overflow:hidden;">' +
        '                    </div>' +
        '                </dd>' +
        '            </dl>' +
        '        </div> ' +
        '      </dd>' +
        '    </dl>' +
        '    </div> ' +
        '  </dd>' +
        '  <dt></dt>' +
        '</dl></div>');

    // Assemble some nodes and set the title.
    content_node
        .appendChild(container)
            .one('#structural-subscription-context-title')
                .set('text', LP.cache.context.title);
    add_recipient_picker(content_node, hide_recipient_picker);

    var accordion = create_accordion('#accordion-overlay', content_node);

    // Set up click handlers for the events radio buttons.
    var radio_group = Y.all('#events input');
    radio_group.on(
        'change',
         function() {handle_change(ADDED_OR_CHANGED, FILTER_WRAPPER);});

    // And a listener for advanced filter selection.
    var advanced_filter = Y.one('#' + ADVANCED_FILTER);
    advanced_filter.on(
        'change',
        function() {handle_change(ADVANCED_FILTER, ACCORDION_WRAPPER);});
    return '#' + container._node.id;
}                               // setup_overlay
// Expose in the namespace for testing purposes.
namespace._setup_overlay = setup_overlay;

function handle_change(control_name, div_name, user_cfg) {
    // Expand or collapse the node depending on the control.
    // user_cfg is passed to expand_node or collapse_node, and is
    // useful to set the duration.
    var ctl = Y.one('#' + control_name);
    var more = Y.one('#' + control_name + '-more');
    var div = Y.one('#' + div_name);
    var checked = ctl.get('checked');
    if (checked) {
        expand_node(div, user_cfg);
        more.setStyle('display', 'none');
    } else {
        collapse_node(div, user_cfg);
        more.setStyle('display', null);
    }
}

/**
 * Create the LP client.
 *
 * @method setup_client
 */
function setup_client() {
    namespace.lp_client = new Y.lp.client.Launchpad();
}                               // setup_client

/**
 * External entry point for configuring the structual subscription.
 * @method setup_bug_subscriptions
 * @param {Object} config Object literal of config name/value pairs.
 *     config.content_box is the name of an element on the page where
 *         the overlay will be anchored.
 */
namespace.setup_bug_subscriptions = function(config) {
    // Return if pre-setup fails.
    if (!pre_setup(config)) {
        return;
    }

    fill_in_bug_subscriptions(config);
};

/**
 * Set up a validator function for a form input field.
 * @method add_input_validator
 * @param {Object} overlay Overlay object.
 * @param {String} overlay_id Element ID of the containing overlay.
 * @param {String} field_name Form <input> 'name' to set up a validator for.
 * @param {String} validator Function which returns 'null' if there is
      no error in the field value, and an error message otherwise.
 */
function add_input_validator(overlay, overlay_id, field_name, validator) {
    var input = Y.one(overlay_id + ' input[name="'+field_name+'"]');
    var field_container = input.get('parentNode');
    var error_container = Y.Node.create('<div class="inline-warning"></div>');
    field_container.appendChild(error_container);

    input.on('change', function(e) {
        var error_text = validator(input.get('value'));
        if (error_text !== null) {
            Y.lp.anim.red_flash({node: input}).run();
            error_container.setContent(error_text);
            overlay.field_errors[field_name] = true;
            // Accordion sets fixed height for the accordion item,
            // so we have to resize the tags container.
            if (field_name === 'tags') {
                tags_container.resize();
            }
            // Firefox prohibits focus from inside the 'focus lost' event
            // handler (probably to stop loops), so we need to run
            // it from a different context (which we do with setTimeout).
            setTimeout(function() { input.focus(); input.select(); }, 1);
        } else {
            error_container.setContent('');
            overlay.field_errors[field_name] = false;
        }
    });
}

function get_error_for_tags_list(value) {
    // See database/schema/trusted.sql valid_name() function
    // which is used to validate a single tag.
    // As an extension, we also allow "-" (hyphen) in front of
    // any tag to indicate exclusion of a tag, and we accept
    // a space-separated list.
    if (value.match(/^(\-?[a-z0-9][a-z0-9\+\.\-]*[ ]*)*$/) !== null) {
        return null;
    } else {
        return ('Tags can only contain lowercase ASCII letters, ' +
                'digits 0-9 and symbols "+", "-" or ".", and they ' +
                'must start with a lowercase letter or a digit.');
    }
}

// Export for testing
namespace._get_error_for_tags_list = get_error_for_tags_list;

function get_input_by_value(node, value) {
    // XXX broken: this should also care about input name because some values
    // repeat in other areas of the form
    return node.one('input[value="'+value+'"]');
}


/**
 * Set the value of a set of checkboxes to the provided values.
 */
function set_checkboxes(node, all, checked) {
    // Clear all the checkboxes.
    Y.each(all, function (value) {
            get_input_by_value(node, value).set('checked', false);
    });
    // Check the checkboxes that are supposed to be checked.
    Y.each(checked, function (value) {
        get_input_by_value(node, value).set('checked', true);
    });
}

/**
 * Set the value of a select box to the provided value.
 */
function set_options(node, name, value) {
    var select = node.one('select[name="team"]');
    Y.each(select.get('options'), function (option) {
            option.set('selected', option.get('value')===value);
        });
}

/**
 * Set the value of a set of radio buttons to the provided value.
 */
function set_radio_buttons(node, all, value) {
    set_checkboxes(node, all, [value]);
}

/**
 * Set the values of the recipient select box and radio buttons.
 */
function set_recipient(node, is_team, team_link) {
    if (LP.cache.administratedTeams.length > 0) {
        get_input_by_value(node, 'user').set('checked', !is_team);
        get_input_by_value(node, 'team').set('checked', is_team);
        set_options(node, 'teams',
                    team_link || LP.cache.administratedTeams[0].link);
    }
}

/**
 * Sets the recipient label according to the filter on the overlay.
 * Overlay must not have a recipient picker, but a simple recipient label.
 */
function set_recipient_label(content_node, filter_info) {
    var recipient_label = content_node.one('input[name="recipient"] + span'),
        teams = LP.cache.administratedTeams;
    if (filter_info !== undefined && filter_info.subscriber_is_team) {
        var team = get_team(filter_info.subscriber_link);
        recipient_label.set('text', team.title);
    } else {
        recipient_label.set('text', 'Yourself');
    }
}

/**
 * Sets filter statuses and importances on the overlay based on the filter
 * data.
 */
function set_filter_statuses_and_importances(content_node, filter) {
    var is_lifecycle = filter.bug_notification_level==='Lifecycle',
        statuses = filter.statuses,
        importances = filter.importances,
        information_types = filter.information_types;
    if (is_lifecycle) {
        statuses = LP.cache.statuses;
        importances = LP.cache.importances;
        information_types = LP.cache.information_types;
    } else {
        // An absence of values is equivalent to all values.
        if (statuses.length === 0) {
            statuses = LP.cache.statuses;
        }
        if (importances.length === 0) {
            importances = LP.cache.importances;
        }
        if (information_types.length === 0) {
            information_types = LP.cache.information_types;
        }
    }
    set_checkboxes(content_node, LP.cache.statuses, statuses);
    set_checkboxes(
        content_node, LP.cache.importances, importances);
    set_checkboxes(
        content_node, LP.cache.information_types, information_types);
}

/**
 * Sets filter tags and tag matching options in the overlay based on the
 * filter data.
 */
function set_filter_tags(content_node, filter) {
    var is_lifecycle = filter.bug_notification_level==='Lifecycle';
    content_node.one('[name="tags"]').set(
        'value', is_lifecycle ? '' : filter.tags.join(' '));
    set_radio_buttons(
        content_node, [MATCH_ALL, MATCH_ANY],
        filter.find_all_tags ? MATCH_ALL : MATCH_ANY);
}

/**
 * Sets filter notification level radio/check boxes in the overlay
 * according to the filter data.
 */
function set_filter_notification_options(content_node, filter) {
    var is_lifecycle = filter.bug_notification_level==='Lifecycle',
        has_advanced_filters = !is_lifecycle && (
            filter.statuses.length ||
                filter.importances.length ||
                filter.information_types.length ||
                filter.tags.length) > 0,
        filters = has_advanced_filters ? [ADVANCED_FILTER] : [],
        event = ADDED_OR_CHANGED;
    // Chattiness: Lifecycle < Details < Discussion.
    switch (filter.bug_notification_level) {
        case 'Lifecycle':
            event = ADDED_OR_CLOSED;
            filters = [];
            break;
        case 'Discussion':
            filters.push(INCLUDE_COMMENTS);
            break;
    }
    // 'Details' case is the default and handled by the declared
    // values in the code.
    set_radio_buttons(
        content_node, [ADDED_OR_CLOSED, ADDED_OR_CHANGED], event);
    set_checkboxes(
        content_node, [INCLUDE_COMMENTS, ADVANCED_FILTER], filters);
    handle_change(ADDED_OR_CHANGED, FILTER_WRAPPER, {duration: 0});
    handle_change(ADVANCED_FILTER, ACCORDION_WRAPPER, {duration: 0});
}

/**
 * Loads all data from the filter into the overlay for editing.
 */
function load_overlay_with_filter_data(content_node, filter_info) {
    var filter = filter_info.filter;
    set_recipient_label(content_node, filter_info);
    content_node.one('[name="name"]').set('value',filter.description);
    set_filter_statuses_and_importances(content_node, filter);
    set_filter_tags(content_node, filter);
    set_filter_notification_options(content_node, filter);
}

/**
 * Show an overlay for editing a subscription.
 */
function show_edit_overlay(config, subscription, filter_info, filter_id) {
    var content_node = Y.one(config.content_box);
    var overlay_id = setup_overlay(config.content_box, true);
    clear_overlay(content_node, true);
    var submit_button = Y.Node.create(
            '<button type="submit" name="field.actions.create" ' +
                'value="Save Changes">Save</button>');

    var context = {
        filter_info: filter_info,
        filter_id: filter_id
    };
    create_overlay(
        config.content_box, overlay_id, submit_button,
        function (form_data) {
            return edit_subscription_handler(context, form_data);});

    load_overlay_with_filter_data(content_node, filter_info);
    var title = subscription.target_title;
    Y.one('#structural-subscription-context-title')
        .set('text', title);
    Y.one('#subscription-overlay-title')
        .set('text', 'Edit subscription for '+title+' bugs');

    // We need to initialize the help links.
    Y.lp.app.inlinehelp.init_help();
    namespace._add_subscription_overlay.show();
}

/**
 * Return an edit handler for the specified filter.
 */
function make_edit_handler(subscription, filter_info, filter_id, config) {
    // subscription is the filter's subscription.
    // filter_info is the filter's information (from subscription.filters).
    // filter_id is the numerical id for the filter, unique on the page.
    // config is the configuration object used for the entire assembly of the
    // page.
    return function(e) {
        e.halt();
        show_edit_overlay(config, subscription, filter_info, filter_id);
    };
}

// If set, this will be used instead of Y.io.  This is for testing.
namespace._Y_io_hook = null;

function do_io(link, config) {
    var yio = Y.io;
    if (namespace._Y_io_hook) {
        yio = namespace._Y_io_hook;
    }
    yio(link, config);
}

/**
 * Construct a handler for an unsubscribe link.
 */
function make_delete_handler(filter, filter_id, node, subscriber_id) {
    var error_handler = new Y.lp.client.ErrorHandler();
    var unsubscribe_node = node.one('a.delete-subscription');
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(unsubscribe_node, error_msg);
    };
    error_handler.clearProgressUI = function () {
        unsubscribe_node.replaceClass('spinner', 'remove');
    };
    return function() {
        var y_config = {
            method: "POST",
            headers: {'X-HTTP-Method-Override': 'DELETE'},
            on: {
                success: function(transactionid, response, args){
                    unsubscribe_node.replaceClass('spinner', 'remove');
                    var filter_node = Y.one(
                        '#subscription-filter-'+filter_id.toString());
                    filter_node.setStyle("margin-top", "0");
                    var subscriber = Y.one(
                        '#subscription-'+subscriber_id.toString());
                    var filters = subscriber.all('.subscription-filter');

                    collapse_node(filter_node, { remove_on_end: true });
                    if (filters.size() <= 1) {
                        collapse_node(subscriber, { remove_on_end: true });
                        var subscription_info = LP.cache.subscription_info;
                        subscription_info[subscriber_id].filters = [];
                    }
                },
                failure: error_handler.getFailureHandler()
            }
        };
        unsubscribe_node.replaceClass('remove', 'spinner');
        do_io(filter.self_link, y_config);
    };
}

/**
 * Construct a handler for a mute link.
 */
function make_mute_handler(filter_info, node){
    var error_handler = new Y.lp.client.ErrorHandler();
    var mute_node = node.one('a.mute-subscription');
    var icon_class = function () {
        if (filter_info.is_muted) {
            return UNMUTE_ICON_CLASS;
        } else {
            return MUTE_ICON_CLASS;
        }
    };
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(mute_node, error_msg);
    };
    error_handler.clearProgressUI = function () {
        mute_node.replaceClass('spinner', icon_class());
    };
    return function() {
        var fname;
        if (filter_info.is_muted) {
            fname = 'unmute';
        } else {
            fname = 'mute';
        }
        var config = {
            on: {success: function(){
                    mute_node.removeClass('spinner');
                    if (fname === 'mute') {
                        filter_info.is_muted = true;
                    } else {
                        filter_info.is_muted = false;
                    }
                    handle_mute(node, filter_info);
                    },
                 failure: error_handler.getFailureHandler()
                }
            };
        mute_node.replaceClass(icon_class(), 'spinner');
        namespace.lp_client.named_post(filter_info.filter.self_link,
            fname, config);
    };
}

/**
 * Figure out if the user can edit a particular structural subscription.
 */
function can_edit(filter_info) {
    return !filter_info.subscriber_is_team || filter_info.user_is_team_admin;
}

/**
 * Attach activation (click) handlers to links for a particular filter.
 */
function wire_up_edit_links_for_filter(
    config, subscription, subscription_id, filter_info, filter_id,
    filter_node) {
    var node = filter_node || Y.one(
        '#subscription-filter-'+filter_id.toString());
    if (filter_info.can_mute) {
        var mute_link = node.one('a.mute-subscription');
        mute_link.on('click', make_mute_handler(filter_info, node));
    }
    if (can_edit(filter_info)) {
        var edit_link = node.one('a.edit-subscription');
        var edit_handler = make_edit_handler(
            subscription, filter_info, filter_id, config);
        edit_link.on('click', edit_handler);
        var delete_link = node.one('a.delete-subscription');
        var delete_handler = make_delete_handler(
            filter_info.filter, filter_id, node, subscription_id);
        delete_link.on('click', delete_handler);
    }
}

/**
 * Attach activation (click) handlers to all of the edit links on the page.
 */
function wire_up_edit_links(config) {
    var listing = Y.one(config.content_box);
    var subscription_info = LP.cache.subscription_info;
    var filter_id = 0;
    var i;
    var j;
    for (i=0; i<subscription_info.length; i++) {
        var sub = subscription_info[i];
        for (j=0; j<sub.filters.length; j++) {
            var filter_info = sub.filters[j];
            wire_up_edit_links_for_filter(
                config, sub, i, filter_info, filter_id);
            filter_id += 1;
        }
    }
}

/**
 * For a given filter node, set it up properly based on mute state.
 */
function handle_mute(node, filter_info) {
    var control = node.one('a.mute-subscription');
    var label = node.one('em.mute-label');
    var description = node.one('.filter-description');
    if (filter_info.is_muted) {
        control.set('text', 'Send me emails for this subscription');
        control.replaceClass(MUTE_ICON_CLASS, UNMUTE_ICON_CLASS);
        label.setStyle('display', null);
        description.setStyle('color', '#bbb');
    } else {
        control.set('text', 'Stop my emails from this subscription');
        control.replaceClass(UNMUTE_ICON_CLASS, MUTE_ICON_CLASS);
        label.setStyle('display', 'none');
        description.setStyle('color', null);
    }
}

/**
 * Create filter node to include in the subscription's filter listing.
 */
function create_filter_node(filter_id, filter_info, filter) {
    var filter_node = Y.Node.create(
        '<div style="margin: 1em 0em 0em 1em"'+
            '      class="subscription-filter"></div>')
        .set('id', 'subscription-filter-'+filter_id.toString());
    filter_node.appendChild(Y.Node.create(
        '<div style="margin-top: 1em"></div>'));
    filter_node.appendChild(Y.Node.create(
        '<strong class="filter-name"></strong>'));

    if (filter_info.can_mute) {
        filter_node.append(Y.Node.create('<em/>')
            .set('text', 'You do not receive emails from this subscription.')
            .addClass('mute-label')
            .setStyle('paddingLeft', '1em'));
    }

    var control = filter_node.appendChild(
        Y.Node.create('<span style="float: right"></span>'));

    if (filter_info.can_mute) {
        var link = control.appendChild(Y.Node.create('<a/>')
            .set('href', '#')
            .addClass('sprite')
            .addClass('js-action')
            .addClass('mute-subscription'));
        var help = control.appendChild(Y.Node.create('<a/>')
            .set('href', '/+help-bugs/structural-subscription-mute.html')
            .set('target', 'help')
            .addClass('sprite')
            .addClass('maybe')
            .addClass('mute-help')
            .addClass('action-icon')
            .setStyle('visibility', 'hidden')
            .set('text', 'Delivery help'));
        control.append(Y.Node.create('<span></span>'));
        // We store a reference to the timeout that will hide the help link so
        // we can cancel it if needed.
        var hide_help_timeout;
        var show_help = function () {
            help.setStyle('visibility', 'visible');
            // Every time we trigger the display of the help link we need to
            // cancel any pending hiding of the help link so it doesn't
            // disappear on us.  If there isn't one pending, this is a NOP.
            clearTimeout(hide_help_timeout);
        };
        var hide_help = function () {
            hide_help_timeout = setTimeout(function () {
                help.setStyle('visibility', 'hidden');
            }, 2000);
        };
        link.on('hover', show_help, hide_help);
        help.on('hover', show_help, hide_help);
    }

    if (can_edit(filter_info)) {
        // User can edit the subscription.
        control.append(Y.Node.create('<a/>')
            .set('href', '#')
            .set('text', 'Edit this subscription')
            .setStyle('marginRight', '2em')
            .addClass('sprite')
            .addClass('modify')
            .addClass('edit')
            .addClass('js-action')
            .addClass('edit-subscription'));
        control.append(Y.Node.create('<a/>')
            .set('href', '#')
            .set('text', 'Unsubscribe')
            .addClass('sprite')
            .addClass('modify')
            .addClass('remove')
            .addClass('js-action')
            .addClass('delete-subscription'));
    }

    if (filter_info.team_has_contact_address
            && !filter_info.user_is_team_admin) {
        var subject = encodeURIComponent(
            'Team contact address and subscriptions');
        var user_participation;
        if (filter_info.user_is_on_team_mailing_list) {
            user_participation = 'subscribe to the team\'s mailing list';
        } else {
            user_participation = 'be a part of the team';
        }
        var message = encodeURIComponent(
            'Hello.  I receive email notifications about bugs in '+
            filter_info.target_title+' because of a team subscription for '+
            filter_info.subscriber_title+'. I would like to continue to '+
            user_participation+', but I would like to receive less email '+
            'from this subscription.  Could you remove the team contact '+
            'email address so that the team members can manage their own '+
            'subscriptions (see '+filter_info.subscriber_url+'), or delete '+
            'or reduce level of the subscription itself (see '+
            filter_info.target_bugs_url+'/+subscriptions)?\n\nThank you.');
        control.append(Y.Node.create('<a/>')
            .set('href', filter_info.subscriber_url+'/+contactuser'+
                '?field.message='+message+'&field.subject='+subject)
            .set('text', 'Request team administrators change'));
    }

    filter_node.append(Y.Node.create('<div/>')
        .setStyle('paddingLeft', '1em')
        .addClass('filter-description'));

    if (filter_info.can_mute) {
        handle_mute(filter_node, filter_info);
    }

    fill_filter_description(filter_node, filter_info, filter);

    return filter_node;
}

// Expose in the namespace for testing purposes.
namespace._create_filter_node = create_filter_node;


/**
 * Create a node with subscription description.
 */
function create_subscription_node(serial_id, subscription_data, filter_id) {
    var node = Y.Node.create(
        '<div style="margin-top: 2em; padding: 0 1em 1em 1em; '+
            'border: 1px solid #ddd;"></div>')
        .set('id', 'subscription-'+serial_id.toString());
    node.appendChild(Y.Node.create('<span/>')
        .setStyle('float', 'left')
        .setStyle('marginTop', '-0.8em')
        .setStyle('backgroundColor', '#fff')
        .setStyle('padding', '0 0.5em'))
        .appendChild('<span>Subscriptions to </span>')
        .appendChild(Y.Node.create('<a></a>')
                     .set('href', subscription_data.target_url)
                     .set('text', subscription_data.target_title));

    for (j=0; j<subscription_data.filters.length; j++) {
        var filter_info = subscription_data.filters[j];
        var filter = filter_info.filter;
        // We put the filters in the cache so that the patch mechanism
        // can automatically find them and update them on a successful
        // edit.  This makes it possible to open up a filter after an edit
        // and see the information you expect to see.
        LP.cache['structural-subscription-filter-'+filter_id.toString()] =
            filter;
        node.append(create_filter_node(filter_id, filter_info, filter));
        filter_id += 1;
    }
    return node;
}

/**
 * Populate the subscription list DOM element with subscription descriptions.
 */
function fill_in_bug_subscriptions(config) {
    validate_config(config);

    var destination = Y.one(config.content_box);
    var top_node = Y.Node.create('<div class="yui-g"></div>');
    var list_node = Y.Node.create(
        '<div id="structural-subscriptions"></div>');
    var subscription_info = LP.cache.subscription_info;
    var i;
    var filter_id = 0;
    top_node.appendChild(list_node);
    for (i=0; i<subscription_info.length; i++) {
        list_node.appendChild(
            create_subscription_node(i, subscription_info[i], filter_id));
        filter_id += subscription_info[i].filters.length;
    }

    destination.appendChild(top_node);

    wire_up_edit_links(config);
}

/**
 * Construct a one-line textual description of a filter's name.
 */
function render_filter_title(filter_info, filter) {
    var title = Y.Node.create('<span></span>');
    var description;
    if (filter.description) {
        description = '"'+filter.description+'"';
    } else {
        description = '(unnamed)';
    }
    if (filter_info.subscriber_is_team) {
        title.appendChild(Y.Node.create('<a></a>'))
            .set('href', filter_info.subscriber_url)
            .set('text', filter_info.subscriber_title);
        title.appendChild(Y.Node.create('<span></span>'))
             .set('text', ' subscription: '+description);
    } else {
        title.set('text', 'Your subscription: '+description);
    }
    return title;
}

/**
 * Construct a textual description of all of filter's properties.
 */
function create_filter_description(filter) {
    var description = Y.Node.create('<div></div>');
    var filter_items = [];
    // Format status conditions.
    if (filter.statuses.length !== 0) {
        filter_items.push(Y.Node.create('<li></li>')
            .set('text', 'have the status(es): ' + filter.statuses.join(', ')));
    }

    // Format importance conditions.
    if (filter.importances.length !== 0) {
        filter_items.push(Y.Node.create('<li></li>')
            .set('text',
                'are of importance: ' + filter.importances.join(', ')));
    }

    // Format information type conditions.
    if (filter.information_types.length !== 0) {
        filter_items.push(Y.Node.create('<li></li>')
            .set('text',
                'are of information type: ' +
                filter.information_types.join(', ')));
    }

    // Format tag conditions.
    if (filter.tags.length !== 0) {
        var tag_desc = Y.Node.create('<li>are tagged with </li>')
            .append(Y.Node.create('<strong></strong>'))
            .append(Y.Node.create('<span> of these tags: </span>'))
            .append(Y.Node.create('<span></span>')
                .set('text', filter.tags.join(', ')));

        if (filter.find_all_tags) {
            tag_desc.one('strong').set('text', 'all');
        } else {
            tag_desc.one('strong').set('text', 'any');
        }
        filter_items.push(tag_desc);
    }

    // If there were any conditions to list, stich them in with an
    // intro.
    if (filter_items.length > 0) {
        var ul = Y.Node.create('<ul class="bulleted"></ul>');
        Y.each(filter_items, function (li) {ul.appendChild(li);});
        description.appendChild(
            Y.Node.create('<span>You are subscribed to bugs that</span>'));
        description.appendChild(ul);
    }

    // Format event details.
    var events; // When will email be sent?
    if (filter.bug_notification_level === 'Discussion') {
        events = 'You will receive an email when any change '+
            'is made or a comment is added.';
    } else if (filter.bug_notification_level === 'Details') {
        events = 'You will receive an email when any changes '+
            'are made to the bug.  Bug comments will not be sent.';
    } else if (filter.bug_notification_level === 'Lifecycle') {
        events = 'You will receive an email when bugs are '+
            'opened or closed.';
    } else {
        throw new Error('Unrecognized events.');
    }
    description.appendChild(Y.Node.create(events));

    return description;
}

/**
 * Check the configuration for obvious faults.
 */
function validate_config(config) {
    if (!Y.Lang.isValue(config)) {
        throw new Error(
            'Missing config for structural_subscription.');
    }
    if (!Y.Lang.isValue(config.content_box)) {
            throw new Error(
                'Structural_subscription configuration has ' +
                'undefined properties.');
    }
}

// Expose in the namespace for testing purposes.
namespace._validate_config = validate_config;

/**
 * Do pre-setup checks and initalizations.
 * Sets up the LP client and ensures the user is logged-in.
 */
function pre_setup(config) {
    validate_config(config);

    // If the user is not logged in, then we need to defer to the
    // default behaviour.
    if (LP.links.me === undefined) {
        return false;
    }
    if (Y.Lang.isValue(config.lp_client)) {
        // Tests can specify an lp_client if they want to.
        namespace.lp_client = config.lp_client;
    } else {
        // Setup the Launchpad client.
        setup_client();
    }
    return true;
}

/**
 * Get team information.
 */
function get_team(url) {
    var teams = LP.cache.administratedTeams;
    var i;
    for (i=0; i<teams.length; i++) {
        if (teams[i].link === url) {
            return teams[i];
        }
    }
}

/**
 * Get team information from the submitted form data.
 */
function get_team_info(form_data) {
    var is_team = (form_data.recipient[0] === "team");
    var link, team, title, url, has_preferredemail;
    if (is_team) {
        link = form_data.team[0];
        team = get_team(link);
        if (team !== undefined) {
            title = team.title;
            url = team.url;
            has_preferredemail = team.has_preferredemail;
        } else {
            is_team = false;
            link = LP.links.me;
            has_preferredemail = true;
        }
    }
    return {
        is_team: is_team,
        has_preferredemail: has_preferredemail,
        link: link,
        title: title,
        url: url
    };
}

/**
 * Get target details from either target_info or first subscription_info.
 */
function get_target_info() {
    if (LP.cache.target_info !== undefined) {
        return LP.cache.target_info;
    } else {
        var info = LP.cache.subscription_info[0];
        return {
            title: info.target_title,
            url: info.target_url};
    }
}

/**
 * Constructs filter info on-the-go.
 */
function construct_filter_info(filter, form_data, target_info) {
    var team_info = get_team_info(form_data);

    var filter_info = {
        filter: filter,
        subscriber_is_team: team_info.is_team,
        user_is_team_admin: team_info.is_team,
        can_mute: team_info.is_team && ! team_info.has_preferredemail,
        subscriber_url: team_info.url,
        subscriber_link: team_info.link,
        subscriber_title: team_info.title,
        target_title: target_info.title,
        target_url: target_info.url
    };
    return filter_info;
}

/**
 * Return a function that adds the newly created filter to the
 * subscription's filter list after it has been saved.
 */

function make_add_subscription_success_handler(config) {
    return function(form_data, filter) {
        if (config.add_filter_description === true) {
            // This way to figure out the ID works only
            // if the page shows exactly one "target" (eg. Firefox).
            var subscriber_id = 0;
            var filter_id;
            var subscriptions_list = Y.one(
                '#subscription-' + subscriber_id.toString());

            var filter_data = filter.getAttrs();
            var target_info = get_target_info();
            var filter_info = construct_filter_info(
                filter_data, form_data, target_info);

            /* Node to flash with green on success. */
            var anim_node;

            var subscription_info;
            if (subscriptions_list === null) {
                // No subscriptions are listed at all.
                filter_id = 0;
                subscription_info = {
                    filters: [filter_info],
                    target_url: target_info.url,
                    target_title: target_info.title
                };
                LP.cache.subscription_info = [subscription_info];

                subscriptions_list = create_subscription_node(
                    0, subscription_info, 0);
                var subscriptions = Y.one("#structural-subscriptions");
                subscriptions.appendChild(subscriptions_list);
                anim_node = subscriptions_list.one("#subscription-filter-0");
            } else {
                // There's at least one filter in the page.
                subscription_info = LP.cache.subscription_info[0];
                filter_id = subscription_info.filters.length;
                subscription_info.filters.push(filter);

                var description_node = create_filter_node(
                    filter_id, filter_info, filter_data);
                subscriptions_list.append(description_node);
                anim_node = description_node;
            }

            wire_up_edit_links_for_filter(
                config, subscription_info, 0,
                filter_info, filter_id, anim_node);
            Y.lp.anim.green_flash({node: anim_node}).run();
        } else {
            // Since there is no filter description to update we need another
            // way to tell the user that the subscription was sucessfully
            // added.  We'll do that by creating an informational message box.
            var description = filter.get('description');
            var header = Y.Node.create('<div/>')
                .setStyle('marginBottom', '1em')
                .append('The subscription')
                .append('&#32;'); // a space
            if (description) {
                header
                    .append('named "')
                    .append(Y.Node.create('<span/>')
                        .set('text', description))
                    .append('"')
                    .append('&#32;'); // a space
            }
            header.append('has been created.');

            Y.one('#request-notifications')
                .empty()
                .append(Y.Node.create('<div/>')
                    // We're creating an informational message box.
                    .addClass('informational')
                    .addClass('message')
                    // The box needs to be a little wider to accomodate the
                    // wordy subscription description.
                    .setStyle('width', '50em')
                    .append(header)
                    .append(create_filter_description(filter.getAttrs())));
        }
    };
}

namespace._make_add_subscription_success_handler =
        make_add_subscription_success_handler;

/**
 * Show the overlay for creating a new subscription.
 */
function show_add_overlay(config) {
    var content_node = Y.one(config.content_box);
    var overlay_id = setup_overlay(config.content_box);
    clear_overlay(content_node, false);

    var submit_button = Y.Node.create(
        '<button type="submit" name="field.actions.create" ' +
        'value="Create subscription">Create</button>');

    var success_callback = make_add_subscription_success_handler(config);

    var save_subscription = make_add_subscription_handler(success_callback);
    create_overlay(config.content_box, overlay_id, submit_button,
                   save_subscription, success_callback);
    // We need to initialize the help links.
    Y.lp.app.inlinehelp.init_help();
    namespace._add_subscription_overlay.show();
    return overlay_id;
}
namespace._show_add_overlay = show_add_overlay;

/**
 * Modify a link to pop up a subscription overlay on click.
 *
 * @method setup_subscription_link
 * @param {Object} config Overlay configuration object.
 * @param {String} link_id Id of the link element.
 */
function setup_subscription_link(config, link_id) {
    // Modify the menu-link-subscribe-to-bug-mail link to be visible.
    var link = Y.one(link_id);
    if (!Y.Lang.isValue(link)) {
        Y.log('No structural subscription link found.', 'debug');
        return;
    }
    link.removeClass('hidden');
    link.addClass('visible');
    link.on('click', function(e) {
        e.halt();
        // Call with the namespace so tests can override it.
        namespace._show_add_overlay(config);
    });
    link.addClass('js-action');
}                               // setup_subscription_links
namespace.setup_subscription_link = setup_subscription_link;

/**
 * External entry point for configuring the structural subscription.
 * @method setup
 * @param {Object} config Object literal of config name/value pairs.
 *     config.content_box is the name of an element on the page where
 *         the overlay will be anchored.
 */
namespace.setup = function(config) {
    // Return if pre-setup fails.
    if (!pre_setup(config)) {
        return;
    }

    // Create the subscription links on the page.
    setup_subscription_link(config, '.menu-link-subscribe_to_bug_mail');
}; // setup

}, '0.1', {requires: [
    'dom', 'node', 'lp.anim', 'lp.ui.formoverlay', 'lp.ui.overlay',
    'lp.ui.effects', 'lp.app.errors', 'lp.client', 'gallery-accordion',
    'lp.app.inlinehelp', 'lp.bugs.tags_entry'
]});
