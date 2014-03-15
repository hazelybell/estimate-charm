/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.translations.importqueue
 * @requires oop, event, node, widget, plugin, overlay, lp.ui.choiceedit
 */

YUI.add('lp.translations.importqueue', function(Y) {

var namespace = Y.namespace('lp.translations.importqueue');

/**
 * HTML for the "this entry has error output" icon.  This does not include the
 * fold/unfold triangle shown next to it.
 */
var base_button = '<span class="info sprite"></span>';

/**
 * HTML for panel showing an entry's error output.  The spinner icon is
 * replaced by the actual error output as it comes in.
 */
var output_panel_html =
    '<tr class="lesser secondary output-panel"><td>' +
    '<div><img src="/@@/spinner" alt="loading..." /></div>' +
    '</td></tr>';

/**
 * Compose HTML for the error-output button: the basic button plus the
 * fold/unfold triangle.
 */
var compose_button = function(shown) {
    return base_button +
        (shown ?
            '<span class="treeExpanded sprite"></span>' :
            '<span class="treeCollapsed sprite"></span>');
};

/**
 * Replace given button (or initial placeholder, if the page is only just
 * rendering) with one in the given state.
 *
 * This removes the entire old button and replaces it with a new one.  That's
 * one sure-fire way of getting rid of the old one's click-event handler,
 * which is otherwise a brittle procedure and at the same time hard to test.
 */
var alter_button = function(button, shown) {
    var button_field = button.get('parentNode');
    var text =
        '<div class="new show-output">' +
        compose_button(shown) +
        '</div>';
    new_button = button_field.create(text);
    button_field.replaceChild(new_button, button);
    new_button.on('click', (shown ? hide_output : show_output));
    return button_field.get('parentNode');
};

/**
 * Remove the error-output panel pointed at by event.
 */
var hide_output = function(e) {
    var row = alter_button(e.currentTarget, false);
    var output_panel = row.next();
    if (output_panel.hasClass("output-panel")) {
        output_panel.get('parentNode').removeChild(output_panel);
    }
};

/**
 * Factory for error-output request (and response handlers) for a given
 * output panel.
 */
namespace._output_loader = function(node) {
    return {
        on: {
            success: function(entry) {
                var output_block = entry.get('error_output');
                var error_pre = node.create('<pre class="wrap"></pre>');
                error_pre.appendChild(document.createTextNode(output_block));
                node.set('innerHTML', '');
                node.appendChild(error_pre);
            },
            failure: function(errcode) {
                node.set(
                    'innerHTML',
                    '<strong>ERROR: could not retrieve output.  ' +
                    'Please try again later.</strong>');
            }
        }
    };
};

/**
 * Button has been clicked.  Reveal output panel and request error output from
 * the Launchpad web service.
 */
var show_output = function(e) {
    var row = alter_button(e.currentTarget, true);
    var table = row.get('parentNode');
    var entry_id = row.get('id');

    var output = table.create(output_panel_html);
    table.insertBefore(output, row.next());

    var entry_uri = '+imports/' + entry_id;
    var div = output.one('div');
    var lp = new Y.lp.client.Launchpad();
    lp.get(entry_uri, namespace._output_loader(div));
};

/**
 * Create a choice widget for a given status picker. The function's signature
 * is meant for it to be called from Node.each for each node that contains
 * a settable status.
 * The base configuration for the widget is taken from the choice_confs array
 * which is defined in a code fragment that is included in the page via TAL.
 */
var init_status_choice = function(content_box, index, list) {
    // Reveal the status widget.
    content_box.removeClass('hidden');
    var conf = choice_confs[index];
    conf.title = 'Change status to';
    conf.contentBox = content_box;
    var status_choice = new Y.ChoiceSource(conf);
    status_choice.showError = function(err) {
        Y.lp.app.errors.display_error(null, err);
    };
    var entry_id = content_box.ancestor(function(node){
        return node.hasClass('import_entry_row');
    }).get('id');
    status_choice.on('save', function(e) {
        var value_box = content_box.one('.value');
        var new_status = status_choice.get('value');
        value_box.setContent(new_status);
        config = {
            on: {
                success: function(entry) {
                    Y.Array.each(conf.items, function(item) {
                        if (item.value === new_status) {
                            value_box.addClass(item.css_class);
                        } else {
                            value_box.removeClass(item.css_class);
                        }
                    });
                }
            },
            parameters: {
                new_status: new_status
            }
        };
        Y.log(config);
        lp_client = new Y.lp.client.Launchpad();
        var entry_uri = '+imports/' + entry_id;
        lp_client.named_post(entry_uri, 'setStatus', config);
    });
    status_choice.render();
};

/**
 * Replace placeholders for error-output buttons
 * with actual buttons, and make them functional.
 */
var init_error_output_buttons = function() {
    var button_markers = Y.all('.show-output');
    button_markers.set('innerHTML', compose_button(false));
    button_markers.on('click', show_output);
};

/**
 * Set up the import queue page.
 */
namespace.initialize_import_queue_page = function (Y) {
    // Set up error output buttons.
    init_error_output_buttons();

    // Set up status pickers.
    Y.all('.status-choice').each(init_status_choice);
    Y.all('.status-select').each(function(content_box, index, list) {
        content_box.addClass('hidden');
        });
    var submit_button = Y.one('#import-queue-submit');
    if (submit_button) {
        submit_button.addClass('hidden');
    }
};
}, "0.1", { "requires": ["oop", "event", "node", "widget", "plugin",
    "overlay", "lp.ui.choiceedit", "lp.client", "lp.client.plugins",
    "lp.app.errors"]});
