/* Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Official bug tags management user interface.
 *
 * @module bugs
 * @submodule official_bug_tags
 */

YUI.add('lp.bugs.official_bug_tags', function(Y) {

var namespace = Y.namespace('lp.bugs.official_bug_tags');

/*
 * official_tags and other_tags hold the lists of tags currently in use.
 */
var official_tags;
var other_tags;

/*
 * Regular expression object for validating new tags. Initialized from a JSON
 * representation of the regular expression used in the server code, embedded
 * in the page.
 */
var valid_name_re = new RegExp(valid_name_pattern);

/**
 * Filter an array using a predicate function.
 *
 * Return a new array containing only items for which the function 'fn' returns
 * true.
 *
 * @method filter_array
 * @param arr {Array} the array to filter.
 * @param fn {Function} a predicate function taking a single parameter - an
 *        item in the array.
 */
var filter_array = function(arr, fn) {
    var new_array = [];
    Y.each(arr, function(item) {
        if (fn(item)) {
            new_array.push(item);
        }
    });
    return new_array;
};

/**
 * Sort an array of tag items alphabetically, in place.
 *
 * @method sort_tags
 * @param tags {Array} an array of tag items. Each item is an object with
 *        a 'tag' property.
 */
var sort_tags = function(tags) {
    tags.sort(function(x, y) {
        if (x.tag === y.tag) {
            return 0;
        } else if (x.tag > y.tag) {
            return 1;
        } else {
            return -1;
        }
    });
};

/**
 * Get an array of official bug tags and their use count.
 *
 * Uses an array of official tags embedded in the page and an array of objects
 * representing used tags.
 *
 * @method get_official_bug_tags
 * @param official_bug_tags {Array} an array of the official bug tags
 */
var get_official_bug_tags = function(official_bug_tags) {
    var tags = [];
    Y.each(official_bug_tags, function(item) {
        var count = used_bug_tags[item];
        if (count === null) {
            count = 0;
        }
        tags.push({tag: item, count: count});
    });
    sort_tags(tags);
    return tags;
};

/**
 * Get an array of unofficial bug tags and their use count.
 *
 * Uses an array of objects representing used tags
 * embedded in the page.
 *
 * @method get_other_bug_tags
 * @param used_bug_tags {Array} an array of currently used tags
 */
var get_other_bug_tags = function(used_bug_tags) {
    var tags = [];
    Y.each(used_bug_tags, function(value, key, obj) {
        if (Y.Array.indexOf(official_bug_tags, key) < 0) {
            tags.push({tag: key, count: value});
        }
    });
    sort_tags(tags);
    return tags;
};

/**
 * Enable or disable the arrow buttons.
 *
 * Check for each tag list whether it contains any selected items and enable
 * the corresponding arrow button only if at least one item is selected.
 *
 * @method enable_arrows
 */
var enable_arrows = function() {
    var official_cbs = Y.all('#official-tags-list input');
    var other_cbs = Y.all('#other-tags-list input');
    var official_cbs_checked = false;
    if (official_cbs !== null) {
        official_cbs.each(function(cb) {
            official_cbs_checked = official_cbs_checked || cb.get('checked');
        });
    }
    var other_cbs_checked = false;
    if (other_cbs !== null) {
        other_cbs.each(function(cb) {
            other_cbs_checked = other_cbs_checked || cb.get('checked');
        });
    }
    Y.one('#remove-official-tags').set('disabled', !official_cbs_checked);
    Y.one('#add-official-tags').set('disabled', !other_cbs_checked);
};


// We can't use element ids with dots in them, so we mangle.
// There must be a simpler and more general way to do this.
var re_alphanum = new RegExp('[a-zA-Z0-9-]');

var mangle_id = function(value) {
    var chars = value.split('');
    chars = Y.Array.map(chars, function(ch) {
        if (ch.match(re_alphanum)) {
            return ch;
        } else {
            return '__' + ch.charCodeAt(0) + '__';
        }
    });
    return chars.join('');
};

/**
 * Create a new list-item node representing a tag in a tag list.
 *
 * The list-item contains a checkbox and a label. After the node is created
 * a click event handler is hooked to the checkbox which highlights the entire
 * node if it's selected and triggers the check for enabling the arrow buttons.
 *
 * @method make_tag_li
 */
var make_tag_li = function(item) {
    if (item.count === 0 || item.count === undefined) {
      item.count = '';
    }
    item._tag_id = mangle_id(item.tag);
    var li_html = Y.Lang.sub([
        '<li id="tag-{_tag_id}">',
        '  <input type="checkbox" id="tag-checkbox-{_tag_id}" />',
        '  <label for="tag-checkbox-{_tag_id}">',
        '    <span>{tag}</span> ',
        '    <span class="tag-used-count">{count}</span>',
        '  </label>',
        '</li>'
        ].join(''),
        item);
    var li_node = Y.Node.create(li_html);
    li_node._tag = item;
    li_node.one('input').on('click', function(e) {
      enable_arrows();
      var cb_node = li_node.one('input');
      if (cb_node.get('checked')) {
        li_node.addClass('selected');
      } else {
        li_node.removeClass('selected');
      }
    });
    return li_node;
};

/**
 * Render the lists of tags.
 *
 * For each tag in the in-memory arrays of used tags, create a list-item node
 * and insert it into the list.
 *
 * @method render_tag_lists
 */
var render_tag_lists = function() {
    var official_tags_ul = Y.one('#official-tags-list');
    var other_tags_ul = Y.one('#other-tags-list');

    official_tags_ul.set('innerHTML', '');
    other_tags_ul.set('innerHTML', '');

    Y.each(official_tags, function(item) {
        official_tags_ul.appendChild(make_tag_li(item));
    });

    Y.each(other_tags, function(item) {
        other_tags_ul.appendChild(make_tag_li(item));
    });
};

/**
 * Save the used tags to the database.
 *
 * Collect all the official tags, insert them into a hidden form and submit to
 * the server.
 *
 * @method save_tags
 */
var save_tags = function() {
    var tags = [];
    Y.each(official_tags, function(item) {
        tags.push(item.tag);
    });
    Y.one('#field-official_bug_tags').set('value', tags.join(' '));
    Y.one('#save-form').submit();
};

/**
 * Return an array of tag objects currently selected by the user.
 *
 * @method get_selected_tags
 * @param tags_ul {Node} the list DOM node to examine.
 */
var get_selected_tags = function(tags_ul) {
    var selected_tags = [];
    tags_ul.all('li').each(function(li) {
        if (li.one('input').get('checked')) {
            selected_tags.push(li._tag);
        }
    });
    return selected_tags;
};

/**
 * Create a shallow copy of an array.
 *
 * @method copy_array
 * @param arr {Array} the array to copy
 */
var copy_array = function(arr) {
    var new_array = [];
    Y.each(arr, function(item) {
        new_array.push(item);
    });
    return new_array;
};

/**
 * Get the updated arrays of tags given a UI list to examine.
 *
 * Returns an object with properties for new versions of the arrays.
 *
 * @method get_updated_tags
 * @param from_tags_ul {Node} the list to examine
 * @param from_tags {Array} the array of tags from which to move items
 * @param to_tags {Array} the array of tags into which to move items
 */
var get_updated_tags = function(from_tags_ul, from_tags, to_tags) {
    var new_from_tags = copy_array(from_tags);
    var new_to_tags = copy_array(to_tags);
    var selected_tags = get_selected_tags(from_tags_ul);
    Y.each(selected_tags, function(item) {
        new_to_tags.push(item);
    });
    new_from_tags = filter_array(from_tags, function(item) {
        return (Y.Array.indexOf(selected_tags, item) < 0);
    });
    sort_tags(new_from_tags);
    sort_tags(new_to_tags);
    return {from_tags: new_from_tags, to_tags: new_to_tags};
};

/**
 * Stuff to do after a new tag is added.
 *
 * Grab the new tag out of the textbox and validate it. If the value doesn't
 * validate display an error message. Otherwise, add the new tag to the list of
 * official tags, clear the textbox and refresh the tag lists and all buttons.
 *
 * @method on_new_tag_add
 */
var on_new_tag_add = function() {
    var new_tag = Y.Lang.trim(Y.one('#new-tag-text').get('value'));
    var new_tag_already_official = false;
    Y.each(official_tags, function(item) {
        new_tag_already_official = (
            new_tag_already_official || (item.tag === new_tag));
    });
    var new_tag_already_used = false;
    Y.each(other_tags, function(item) {
        new_tag_already_used = (
            new_tag_already_used || (item.tag === new_tag));
    });
    if (new_tag_already_used) {
        Y.each(other_tags, function(item) {
            if (item.tag === new_tag) {
                official_tags.push(item);
            }
        });
        other_tags = filter_array(other_tags, function(item) {
            return item.tag !== new_tag;
        });
    }
    if (!new_tag_already_official && !new_tag_already_used) {
        if (valid_name_re.test(new_tag)) {
            var count = used_bug_tags[new_tag];
            if (count === null) {
                count = 0;
            }
            official_tags.push({tag: new_tag, count: 0});
            sort_tags(official_tags);
            Y.one('#new-tag-text').set('value', '');
            Y.one('#new-tag-add').set('disabled', true);
            Y.one('#save-button').set('disabled', false);
        } else {
            display_error();
        }
    }
    render_tag_lists();
};

var ERROR_MSG = ['<div class="official-tag-error-message">',
                 '<span class="official-tag-error-message-value">',
                 '{new_tag}</span>',
                 'is not a valid tag name.',
                 'Tags must start with a letter or number and be lowercase.',
                 'The characters "+", "-" and "." are also allowed after the',
                 'first character.',
                 '</div>'].join(' ');

/**
 * Display an error message when a proposed tag is invalid.
 *
 * @method display_error
 */
var display_error = function() {
    var new_tag = Y.one('#new-tag-text').get(
        'value').replace(new RegExp('<', 'g'), '&lt;');
    var overlay = new Y.lp.ui.PrettyOverlay({
      headerContent: '<span class="official-tag-error-message-header">' +
                     '<img src="/@@/error" />&nbsp;Invalid Tag</span>',
      bodyContent: Y.Lang.sub(ERROR_MSG, {new_tag: new_tag}),
      align: {
        points: [Y.WidgetPositionAlign.CC, Y.WidgetPositionAlign.CC]
      },
      progressbar: false,
      progress: 0
    });
    overlay.render();
};

/**
 * Set up the dynamic interface for managing official bug tags.
 *
 * Called once, as soon as the DOM is ready, to initialize the page.
 *
 * @method setup_official_bug_tag_management
 */
namespace.setup_official_bug_tag_management = function() {
    official_tags = get_official_bug_tags(official_bug_tags);
    other_tags = get_other_bug_tags(used_bug_tags);

    var layout_table = Y.one('#layout-table');

    // The entire dynamic UI is hidden initially, so that clients
    // with no JS don't display it.
    layout_table.setStyle('display', 'block');

    var official_tags_ul = Y.one('#official-tags-list');
    var other_tags_ul = Y.one('#other-tags-list');

    render_tag_lists();

    // Hook an event handler to the arrow button for moving
    // tags from the list of unofficial tags to the list of official tags.
    Y.one('#add-official-tags').on('click', function(e) {
        var updated_tags = get_updated_tags(
            other_tags_ul, other_tags, official_tags);
        other_tags = updated_tags.from_tags;
        official_tags = updated_tags.to_tags;
        render_tag_lists();
        enable_arrows();
        Y.one('#save-button').set('disabled', false);
    });

    // Hook an event handler to the arrow button for moving
    // tags from the list of official tags to the list of unofficial tags.
    Y.one('#remove-official-tags').on('click', function(e) {
        var updated_tags = get_updated_tags(
            official_tags_ul, official_tags, other_tags);
        official_tags = updated_tags.from_tags;
        other_tags = updated_tags.to_tags;
        render_tag_lists();
        enable_arrows();
        Y.one('#save-button').set('disabled', false);
    });

    Y.one('#new-tag-add').on('click', function(e) {
        on_new_tag_add();
    });

    // Hook a keypress event handler to the new tag text box. If enter is
    // pressed, try adding a new tag.
    Y.one('#new-tag-text').on('keypress', function(e) {
        var new_value = Y.Lang.trim(Y.one('#new-tag-text').get('value'));
        Y.one('#new-tag-add').set('disabled', new_value === '');
        if (e.keyCode === 13) {  // Enter == 13
            on_new_tag_add();
        }
    });

    Y.one('#save-button').on('click', function(e) {
        e.halt();
        save_tags();
    });

    // All went well, hide the plain html form.
    Y.one('form[name="launchpadform"]').setStyle('display', 'none');
};
}, "0.1", {
    "requires": ["array-extras", "node", "substitute", "base", "collection",
                 "lp.ui.overlay"]
});
