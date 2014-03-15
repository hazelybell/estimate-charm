/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Inline bug tags entry with auto suggestion.
 *
 * @module bugs
 * @submodule bug_tags_entry
 */

YUI.add('lp.bugs.tags_entry', function(Y) {

var namespace = Y.namespace('lp.bugs.tags_entry');

var bug_tags_div;
var tags_heading;
var tags_trigger;
var tag_list_span;
var tag_input;
var ok_button;
var cancel_button;
var tags_edit_spinner;
var tags_form;
var available_tags;
var autocomplete;

var A = 'a',
    VALUE = 'value',
    BUG = 'bug',
    INNER_HTML = 'innerHTML',
    ESCAPE = 27,
    HIDDEN = 'hidden';

/**
 * Grab all existing tags and insert them into the input
 * field for editing.
 *
 * @method populate_tags_input
 */
var populate_tags_input = function() {
    var tags = [];

    tag_list_span.all(A).each(function(anchor) {
        tags.push(anchor.get(INNER_HTML));
    });

    var tag_list = tags.join(' ');
    /* If there are tags then add a space to the end of the string so the user
       doesn't have to type one. */
    if (tag_list !== "") {
        tag_list += ' ';
    }
    tag_input.set(VALUE, tag_list);
};

/**
 * The base URL for tag searches. Append a tag to get a tag search URL.
 */
var base_url = window.location.href.split('/+bug')[0] + '/+bugs?field.tag=';

namespace.parse_tags = function(tag_string) {
    var tags  = Y.Array.filter(
        Y.Lang.trim(tag_string).split(new RegExp('\\s+')),
        function(elem) { return elem !== ''; });
    return tags;
};


namespace.lp_config = {};


/**
 * Save the currently entered tags and switch inline editing off.
 *
 * @method save_tags
 */
var save_tags = function() {
    var lp_client = new Y.lp.client.Launchpad(namespace.lp_config);
    var tags = namespace.parse_tags(tag_input.get(VALUE));
    var bug = new Y.lp.client.Entry(
        lp_client, LP.cache[BUG], LP.cache[BUG].self_link);
    bug.removeAttr('http_etag');
    bug.set('tags', tags);
    namespace.show_activity(true);
    bug.lp_save({on : {
        success: function(updated_entry) {
            var official_tags = [];
            var unofficial_tags = [];
            Y.each(updated_entry.get('tags'), function(tag) {
                if (Y.Array.indexOf(available_tags, tag) > -1) {
                    official_tags.push(tag);
                } else {
                    unofficial_tags.push(tag);
                }
            });
            official_tags.sort();
            unofficial_tags.sort();
            var tags_html = Y.Array.map(official_tags, function(tag) {
                return Y.Lang.sub(
                    '<a href="{tag_url}" class="official-tag">{tag}</a>',
                    {tag_url: base_url + tag, tag: tag});
            }).join(' ') + ' ' + Y.Array.map(unofficial_tags, function(tag) {
                return Y.Lang.sub(
                    '<a href="{tag_url}" class="unofficial-tag">{tag}</a>',
                    {tag_url: base_url + tag, tag: tag});
            }).join(' ');
            tag_list_span.set(INNER_HTML, tags_html);
            tag_list_span.removeClass(HIDDEN);
            tags_trigger.removeClass(HIDDEN);
            namespace.show_activity(false);
            tags_form.addClass(HIDDEN);
            Y.lp.anim.green_flash({ node: tag_list_span }).run();
            namespace.update_ui();
        },
        failure: function(id, request) {
            namespace.show_activity(false);
            Y.lp.anim.red_flash({ node: tag_list_span }).run();
        }
    }});
};

/**
 * Cancel editing - hide the inline editor and restore the tags display.
 *
 * @method cancel
 */
var cancel = function() {
    tag_list_span.removeClass(HIDDEN);
    tags_trigger.removeClass(HIDDEN);
    tags_form.addClass(HIDDEN);
    autocomplete.hide();
    Y.lp.anim.green_flash({ node: tag_list_span }).run();
    namespace.update_ui();
};

/**
 * Start editing - show the inline editor and populate it.
 *
 * @method edit
 */
var edit = function() {
    populate_tags_input();
    tag_list_span.addClass(HIDDEN);
    tags_trigger.addClass(HIDDEN);
    tags_form.removeClass(HIDDEN);
    tag_input.focus();
    autocomplete.render();
};


/**
 * Update the spinner and buttons to show activity or no activity.
 *
 * @method show_activity
 */
namespace.show_activity = function(active) {
    if (active) {
        tags_edit_spinner.removeClass(HIDDEN);
        ok_button.addClass(HIDDEN);
        cancel_button.addClass(HIDDEN);
    } else {
        tags_edit_spinner.addClass(HIDDEN);
        ok_button.removeClass(HIDDEN);
        cancel_button.removeClass(HIDDEN);
    }
};

/**
 * Update the heading and action to match the tag state.
 *
 * @method update_ui
 */
namespace.update_ui = function() {
    if (Y.Lang.trim(tag_list_span.get('innerHTML')) === '') {
        // Show the add tags presentation.
        tags_heading.set('text', '');
        tags_trigger.setAttrs(
            {'text': 'Add tags',
             'title': 'Add tags'});
        tags_trigger.removeClass('edit');
        tags_trigger.removeClass('action-icon');
        tags_trigger.addClass('add');
    } else {
        // Show the edit tags presentation.
        tags_heading.set('text', 'Tags:');
        tags_trigger.setAttrs(
            {'text': 'Edit',
             'title': 'Edit tags'});
        tags_trigger.removeClass('add');
        tags_trigger.addClass('edit');
        tags_trigger.addClass('action-icon');
    }
};


/**
 * Set up inline tag editing on a bug page.
 *
 * @method setup_tag_entry
 */
namespace.setup_tag_entry = function(available_official_tags) {
    if (LP.links.me === undefined) { return; }

    available_tags = available_official_tags;
    bug_tags_div = Y.one('#bug-tags');
    tags_heading = bug_tags_div.one('#tags-heading');
    tags_trigger = bug_tags_div.one('#tags-trigger');
    tag_list_span = bug_tags_div.one('#tag-list');

    tag_input = Y.Node.create(
        '<input type="text" id="tag-input" />');
    tags_edit_spinner = Y.Node.create(
        '<img src="/@@/spinner" id="tags-edit-spinner" class="hidden" />');
    ok_button = Y.Node.create(
        '<button class="lazr-pos lazr-btn yui-ieditor-submit_button" ' +
        'id="edit-tags-ok" type="button">Ok</button>');
    cancel_button = Y.Node.create(
        '<button class="lazr-neg lazr-btn yui-ieditor-cancel_button" ' +
        'id="edit-tags-cancel" type="button">Cancel</button>');
    tags_form = Y.Node.create(
        '<form id="tags-form" class="inline hidden"></form>');
    tags_form.append(new Y.NodeList([
        tag_input, tags_edit_spinner, ok_button, cancel_button]));
    tag_list_span.insert(tags_form, 'after');

    tag_input.on('keydown', function(e) {
            if (e.keyCode === ESCAPE) {
                e.halt();
                cancel();
            }
        });
    ok_button.on('click', function(e) {
            e.halt();
            save_tags();
            /* Check to see if the autocomplete dialogue is still open
               and if so, close it. */
            if (!autocomplete._last_input_was_completed) {
                autocomplete.hide();
            }
        });
    cancel_button.on('click', function(e) {
            e.halt();
            cancel();
        });
    tags_form.on('submit', function(e) {
            e.halt();
            save_tags();
        });
    tags_trigger.on('click', function(e) {
        e.halt();
        edit();
    });
    tags_trigger.addClass('js-action');

    autocomplete = namespace.setup_tag_complete(
        '#tag-input', available_official_tags);
};


/**
 * Set up bug tag autocompletion on a text input.
 *
 * @method setup_tag_complete
 */
namespace.setup_tag_complete = function(input, official_tags) {
    var bounding_box = Y.Node.create(
        '<div class="bug-tag-complete"><div></div></div>');
    Y.one('body').appendChild(bounding_box);
    var autocomplete = new Y.lp.ui.AutoComplete({
        input: input,
        data: official_tags,
        boundingBox: bounding_box,
        contentBox: bounding_box.one('div')
    });
    autocomplete.get('input').on('focus', function(e) {
        autocomplete.render();
    });
    return autocomplete;
};
}, "0.1", {
    "requires": [
        "array-extras", "base", "io-base", "node", "substitute",
        "node-menunav", "lp.anim", "lp.ui.autocomplete", "lp.client"]
});
