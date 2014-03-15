/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.autocomplete', function(Y) {

/**
 * A simple autocomplete widget.
 *
 * @module lp.ui.autocomplete
 * @namespace lp.ui.autocomplete
 */

Y.namespace('lp.ui.autocomplete');


var AUTOCOMP     = 'autocomplete',
    BOUNDING_BOX = 'boundingBox',
    CONTENT_BOX  = 'contentBox',

    INPUT   = 'input',
    VALUE   = 'value',
    QUERY   = 'query',
    DATA    = 'data',
    MATCHES = 'matches',
    RENDERED = 'rendered',
    DELIMITER = 'delimiter',

    TAB = 9,
    RETURN = 13,
    ESCAPE = 27,
    ARROW_DOWN = 40,

    getCN = Y.ClassNameManager.getClassName,

    C_LIST = getCN(AUTOCOMP, 'list');


// We need a base class on which to build our autocomplete widget, so we will
// make that class capable of positioning itself, too.
var AutoCompleteBase = Y.Base.build(
    "AutoCompleteBase", Y.Widget, [Y.WidgetStack]);


/**
 * A simple autocomplete widget.
 *
 * @class AutoComplete
 */

function AutoComplete() {
    AutoComplete.superclass.constructor.apply(this, arguments);
}

AutoComplete.NAME = 'autocomplete';

AutoComplete.LIST_TEMPLATE = '<ul></ul>';
AutoComplete.ITEM_TEMPLATE = '<li class="item yui3-menuitem"></li>';
AutoComplete.ITEM_CONTENT_TEMPLATE = (
    '<a href="#" class="yui3-menuitem-content"></a>');

AutoComplete.ATTRS = {
    /**
     * The autocomplete data that we will be filtering to find matching
     * results.
     *
     * @attribute data
     * @type Hash
     * @default Obj
     */
    data: {
        valueFn: function() { return {}; }
    },

    /**
     * The delimiter to use when splitting the user's current input into
     * matchable query strings.
     *
     * @attribute delimiter
     * @type String
     * @default ' '
     */
    delimiter: {
        value: ' '
    },

    /**
     * The current subset of data matching the user's query, ordered by
     * accuracy.  Contains an Array of hash objects; see
     * <code>filterResults</code>' return type for the details.
     *
     * @attribute matches
     * @type Array
     * @default []
     */
    matches: {
        valueFn: function() { return []; }
    },

    /**
     * The DOM element we watch for new input.  May be set with a Node,
     * HTMLElement, or CSS selector.  Setting this aligns the widget's
     * position.
     *
     * @attribute input
     * @type Node
     * @default null
     */
    input: {
        value: null,
        setter: function(val) {
            return this._setInput(val);
        }
    },

    /**
     * The user's current query.  Contains a hash of values containing the
     * current query text, and the query offset.  <code>null</code> if the
     * widget doesn't contain a valid query.
     *
     * See the <code>parseQuery</code> method for the hash details.
     *
     * @attribute query
     * @type Object
     * @default null
     */
    query: {
        value: null
    }
};

Y.extend(AutoComplete, AutoCompleteBase, {

    /**
     * The <ul> containing the current list of completions.  May be null.
     *
     * @property _completions
     * @private
     */
    _completions: null,

    /**
     * Flag to indicate that the user just completed a string
     *
     * @property _last_input_was_completed
     * @private
     */
    _last_input_was_completed: false,

    /**
     * Initialize the widget.
     *
     * @method initializer
     * @protected
     */
    initializer: function() {
        // The widget starts out hidden.
        this.hide();
    },

    /**
     * Destroy the widget.
     *
     * @method destructor
     * @protected
     */
    destructor: function() {
        // Detach our keyboard input listener
        var input = this.get('INPUT');
        if (input && this.get(RENDERED)) {
            input.detach('keydown', this._onInputKeydown);
            input.detach('keyup', this._onInputKeyup);
        }
    },

    /**
     * Render the DOM and position the widget.
     *
     * @method renderUI
     * @protected
     */
    renderUI: function() {
        var input = this.get(INPUT);
        var bounding_box = this.get(BOUNDING_BOX);
        // Needed by the NodeMenuNav plugin
        bounding_box.addClass("yui3-menu");
        // Move ourself into position below the document body.  This is
        // necessary so that the absolute widget positioning code sets
        // the correct coordinates.
        Y.one('body').appendChild(bounding_box);
        this.get(CONTENT_BOX)
            .setStyle('minWidth', input.get('offsetWidth') + "px")
            .addClass('yui3-menu-content');

        // Set the correct absolute coordinates on-screen.  Bypass the
        // Widget.move() function, since it incorrectly positions the element
        // relative to the viewportal scroll.
        var iregion = input.get('region');
        bounding_box.setStyles({
            'left': iregion.left   + 'px',
            'top':  iregion.bottom + 'px'
        });
        // Disable the browser autocomplete so that it does not conflict.
        input.setAttribute('autocomplete', 'off');
    },

    /**
     * Render the completions list.  Swaps out the existing list if one is
     * already present.
     *
     * @method _renderCompletions
     * @param query {String} The user's current query, used for formatting.
     * @protected
     */
    _renderCompletions: function(query) {
        var matches = this.get(MATCHES);
        if (!this.get(RENDERED) || !matches) {
            // Skip lots of rendering work, because if there are no matches,
            // then the autocomplete list will be hidden.
            return;
        }

        var list = Y.Node.create(AutoComplete.LIST_TEMPLATE);
        list.addClass(C_LIST);

        var result;
        var item;
        var match;
        var idx;
        for (idx = 0; idx < matches.length; idx++) {
            match  = matches[idx];
            result = this.formatResult(match.text, query, match.offset);
            item   = this._renderCompletion(result, idx);
            list.appendChild(item);
        }

        var cbox = this.get(CONTENT_BOX);

        var box = this.get(BOUNDING_BOX);
        box.unplug(Y.Plugin.NodeMenuNav);

        if (this._completions) {
            cbox.replaceChild(list, this._completions);
        } else {
            cbox.appendChild(list);
        }

        // Re-plug the MenuNav, so it updates the menu options.
        box.plug(Y.Plugin.NodeMenuNav);
        box.setStyle('z-index', '31000');

        // Highlight the first item.
        this._selectItem(0, false);

        this._completions = list;
    },

    /**
     * Render a completion list item.
     *
     * @method _renderCompletion
     * @protected
     * @param html_content {String} The completion's HTML text content.
     * @param item_index {NUM} The index of this completion item in the list.
     * @return {Node} The new list item.
     */
    _renderCompletion: function(html_content, item_index) {
        var item = Y.Node.create(AutoComplete.ITEM_TEMPLATE);
        item.setAttribute('id', this._makeItemID(item_index));

        var link = Y.Node.create(AutoComplete.ITEM_CONTENT_TEMPLATE);
        link.set('innerHTML', html_content);
        item.appendChild(link);

        return item;
    },

    /**
     * Generate a new item identifier string for a given item index.
     *
     * @method _makeItemID
     * @protected
     * @param index {NUM} The index of the item in the matches list.
     * @return {String} The generated ID.
     */
    _makeItemID: function(index) {
        return 'item' + index;
    },

    /**
     * Retrieve the given item node's index in the match list.
     *
     * @method _indexForItem
     * @protected
     * @param item {Node} The item node to retrieve the index from.
     * @return {NUM} The index as an integer, null if the index couldn't
     *   be retrieved.
     */
    _indexForItem: function(item) {
        var id = parseInt(item.getAttribute('id').replace('item', ''), 10);
        return Y.Lang.isNumber(id) ? id : null;
    },

    /**
     * Bind the widget to the DOM.
     *
     * @method bindUI
     * @protected
     */
    bindUI: function() {
        // Save the handle so we can detach it later.
        var input = this.get(INPUT);
        input.on('keydown', this._onInputKeydown, this);
        input.on('keyup',   this._onInputKeyup,   this);
        this.get('contentBox').on('click', this._onListClick, this);
    },

    /**
     * Parse the user's input, returning the specific query string to be
     * matched.  Returns null if the query is empty (with no characters typed
     * yet).
     *
     * @method parseQuery
     * @public
     * @param input {String} The textbox input to be parsed.
     * @param caret_pos {NUM} Optional: the position of the caret.  Defaults
     *   to the end of the string.
     * @return {Object} A hash containing:
     *   <dl>
     *     <dt>text</dt><dd>The query text</dd>
     *     <dt>offset</dt><dd>The starting index of the query in the input</dd>
     *   </dl>.
     *   Returns <code>null</code> if the query couldn't be parsed.
     */
    parseQuery: function(input, caret_pos) {
        if (caret_pos <= 0) {
            // The caret is as the start of the input field, so no query
            // is possible.
            return null;
        }

        if (!Y.Lang.isNumber(caret_pos) || (caret_pos > input.length)) {
            caret_pos = input.length;
        }

        var delimiter = this.get(DELIMITER);

        // Start searches at the character before the cursor in the string.
        var start = input.lastIndexOf(delimiter, caret_pos - 1);
        var end = input.indexOf(delimiter, caret_pos - 1);

        if ((start === end) && (start !== -1)) {
            // The caret was on the delimiter itself.
            return null;
        }

        if (start === -1) {
            // There wasn't a delimiter between the caret and the start of the
            // string.
            start = 0;
        } else {
            // Move one character past the delimiter
            start++;
        }

        if (end === -1) {
            // There wasn't a delimiter between the caret and the end of the
            // string.
            end = input.length;
        }

        // Strip any leading whitespace.
        while ((input[start] === ' ' || input[start] === '\t')
                && (start <= end)) {
            start++;
        }

        if (start === end) {
            // The whitespace stripping took us to the end of the input.
            return null;
        }

        var query = {
            text:   input.substring(start, end),
            offset: start
        };
        return query;
    },

    /**
     * Find inputs matching the user query and update the <em>matches<em>
     * attribute with the result.
     *
     * @method findMatches
     * @public
     * @param query {String} The user query we want to find matches for.
     * @return The array of matches, or an empty array if no results were
     *     found.
     */
    findMatches: function(query) {
        var matches = this.filterResults(this.get(DATA), query);
        this.set(MATCHES, matches);
        return matches;
    },

    /**
     * Filter the widget's data set down to the matching results.
     *
     * The returned list of matches is in order of priority.
     *
     * The default implementation puts the matches closest to the front of the
     * user query first.  Matches are case-insensitive.
     *
     * @method filterResults
     * @public
     * @param results {Array} The data to filter
     * @param query {String} The user's current query
     * @return Array of filtered and ordered match objects.  Each match object
     *     has the following keys:
     *     <dl>
     *       <dt>text</dt>
     *       <dd>The query text</dd>
     *       <dt>offset</dt>
     *       <dd>The starting index of the query in the input</dd>
     *     </dl>
     */
    filterResults: function(data, query) {
        // Find matches and push them into an array of arrays.  The array
        // is indexed by the start of the match.

        var midx;
        var match_key;
        var match_string;
        var start_indicies = [];

        var lowercase_query = query.toLowerCase();

        if (data) {
            Y.Array.each(data, function(match_key) {

                match_string = match_key.toString();
                midx = match_string.toLowerCase().indexOf(lowercase_query);

                if (midx > -1) {
                    if (!start_indicies[midx]) {
                        start_indicies[midx] = [];
                    }
                    start_indicies[midx].push(match_string);
                }
            });
        }

        // Flatten the array of match indicies.  Matches close to the front
        // of the user query have a higher priority, and come first in the
        // list of matches.  Matches farther toward the end coming later.
        var matches = [];
        Y.Array.each(start_indicies, function(match_set, index) {
            if (match_set) {
                Y.Array.each(match_set, function(match) {
                    matches.push({text: match, offset: index});
                });
            }
        });

        return matches;
    },

    /**
     * Format a possible completion for display.
     *
     * The returned string will appear as a list item's contents.
     *
     * @method formatResult
     * @public
     * @param result {String} The result data to format.
     * @param query {String} The user's current query.
     * @param offset {NUM} The offset of the matching text in the result.
     * @return {String} The HTML to be displayed.
     */
    formatResult: function(result, query, offset) {
        return this.markMatchingText(result, query, offset);
    },

    /**
     * Mark the portion of a result that matches the user query.
     *
     * @method markMatchingText
     * @public
     * @param text {String} The completion result text to be marked.
     * @param query {String} The user query string.
     * @param offset {NUM} The offset of the query in the text.
     * @return {String} The modified text.
     */
    markMatchingText: function(text, query, offset) {
        var start = offset;
        if (start < 0 || !query) {
            return text;
        }

        var end = start + query.length;

        var before = text.substring(0, start);
        var match  = text.substring(start, end);
        var after  = text.substring(end);

        // This is ugly, but I can't see a better way to do it at the moment.
        match = '<span class="matching-text">' + match + '</span>';

        return before + match + after;
    },

    /**
     * Complete the user's input using the item currently selected in the
     * completions list, or the first item if no list item was picked.
     *
     * @method completeInput
     * @public
     */
    completeInput: function() {
        var active_item = this.getActiveItem();
        if (active_item) {
            var item_index = this._indexForItem(active_item);
            if (item_index !== null) {
                this.completeInputUsingItem(item_index);
            }
        } else {
            // Select the first item in the list
            this.completeInputUsingItem(0);
        }
        this.get(INPUT).focus();
        this._last_input_was_completed = true;
    },

    /**
     * Completes the user's input using the specified match number.
     *
     * @method completeInputUsingItem
     * @public
     * @param match_num {NUM} The number of the match to select.
     */
    completeInputUsingItem: function(match_num) {
        var matches = this.get(MATCHES);
        if (matches.length === 0) {
            return;
        }

        if (match_num >= matches.length) {
            Y.fail("Failed to complete item number " + match_num +
                " because there are only " + matches.length + " matches " +
                "available.");
            return;
        }

        var completion_txt = matches[match_num].text;
        var query = this.get(QUERY);
        var delimiter = this.get(DELIMITER);
        var input = this.get(INPUT);
        var input_txt = input.get('value');

        // Drop the current query from the input string.
        var query_end = query.offset + query.text.length;
        var input_head = input_txt.substring(0, query.offset);
        var input_tail = input_txt.substring(query_end, input_txt.length);
        var tail_delimiter = delimiter;
        // Add the delimiter only if it's needed.
        if (input_tail.charAt(input_tail.length - 1) === delimiter) {
            tail_delimiter = '';
        }

        var new_input = [
            input_head, completion_txt, input_tail, tail_delimiter].join('');

        input.set(VALUE, new_input);
        this.hide();
    },

    /**
     * Return the currently selected item in the completions list.
     *
     * @method getActiveItem
     * @public
     * @return {Node} The selected item node, or null if no item is active.
     */
    getActiveItem: function() {
        // It is ugly to have to check protected members of the menu
        // like this, but the 'currently selected item' should
        // really be public, don't you think?
        var menu = this.get(BOUNDING_BOX).menuNav;
        if (menu) {
            return menu._activeItem ? menu._activeItem : null;
        }
        return null;
    },

    /**
     * Select the Nth item in the completions list.
     *
     * @method _selectItem
     * @protected
     * @param index {NUM} The index of the item to select.
     * @param set_focus {Boolean} Set this to true if the selected item should
     * also recieve the keyboard focus.
     * @return {Node} The item that was selected, or null if it could not
     * be found.
     */
    _selectItem: function(index, set_focus) {
        var menu = this.get(BOUNDING_BOX).menuNav;

        // More ugliness, looking at protected object members that should
        // be made public.
        var firstItem = menu._rootMenu.all('.yui3-menuitem').item(0);
        var item = menu ? firstItem : null;
        if (!menu || !item) {
            return null;
        }

        var idx;
        for (idx = 0; idx < index; idx++) {
            item = item.next();
            if (!item) {
                return null;
            }
        }

        if (set_focus) {
            // We need an anchor to focus on, because some browsers (IE, ahem)
            // don't like focusing non-anchor things.
            var anchor = item.one('a');

            menu._focusManager.set("activeDescendant", anchor);
            menu._focusItem(item);

            if (anchor) {
                // Use a 5ms timer to give the browser rendering engine some
                // time to catch up to the JS call, and prevent a race
                // condition with the focus() method.
                Y.later(5, anchor, anchor.focus);
            }
        }
        menu._setActiveItem(item);
        return item;
    },

    /**
     * Set the autocomplete's <input> element, and align the autocomplete
     * widget's position to it.
     *
     * @method _setInput
     * @protected
     * @param node {Node|HTMLElement|Selector} The input node.
     * @return {Node} A Node instance, or null if the requested input node
     * could not be found.
     */
    _setInput: function(elem) {
        var node = Y.one(elem);
        if (node === null) {
            return null;
        }

        // We need to calculate the input area's caret position.
        Y.augment(node, Y.lp.ui.NodeCaretPos);
        return node;
    },

    /**
     * Handle new text inputs.
     *
     * @method _onInputKeyup
     * @protected
     * @param e {Event.Custom} The event object.
     */
    _onInputKeyup: function(e) {
        var input = this.get(INPUT);
        var caret_pos = null;

        if (input.getCaretPos !== undefined) {
            caret_pos = input.getCaretPos();
        }

        var query = this.parseQuery(input.get(VALUE), caret_pos);
        this.set(QUERY, query);

        if (e.keyCode === ESCAPE ||
            e.keyCode === RETURN ||
            e.keyCode === TAB ||
            e.keyCode === ARROW_DOWN) {
            // We don't want to re-display the matches list.
            return;
        }

        if (query === null) {
            // No valid user input yet
            this._last_input_was_completed = false;
            this.hide();
            return;
        }

        if (this.findMatches(query.text).length !== 0) {
            this._renderCompletions(query.text);
            this._last_input_was_completed = false;
            this.show();
        } else {
            this.hide();
        }
    },

    /**
     * Handle presses of keys like Tab and Enter
     *
     * @method _onInputKeydown
     * @protected
     * @param e {Event.Custom} The event object.
     */
    _onInputKeydown: function(e) {
        // Is this one of our completion keys; Tab, or Enter?
        if (e.keyCode === TAB || e.keyCode === RETURN) {
            /* Check that the last string was not completed and that there are
               matching queries (we don't want to try and complete the input if
               there are no matches). */
            if (this.get(QUERY) !== null
                && !this._last_input_was_completed
                && this.findMatches(this.get(QUERY).text).length !== 0) {
                // The user has an active query in the input box.
                this.completeInput();
                // Keep the tab key from switching focus away from the input
                // field.
                e.preventDefault();
            }
        } else if (e.keyCode === ESCAPE) {
            // Escape closes the currently displayed results
            this.hide();
        } else if (e.keyCode === ARROW_DOWN) {
            this._selectItem(1, true);
            // Prevent the browser from scrolling the window.
            e.preventDefault();
        }
    },

    /**
     * Handle clicks on the autocomplete widget list.
     *
     * @method _onListClick
     * @protected
     * @param e {Event.Custom} The event object.
     */
    _onListClick: function(e) {
        this.completeInput();
        e.preventDefault();
    }
});


Y.lp.ui.AutoComplete = AutoComplete;


/**
 * A mixin class for calculating the caret position inside a Node
 * instance.
 *
 * @class NodeCaretPos
 */

Y.lp.ui.NodeCaretPos = function() {};

/**
 * Return the offset of the caret in a text field.
 *
 * @method getCaretPos
 * @public
 * @return {NUM} The distance from the start of the field to the caret, or
 *     null if the position couldn't be calculated.
 */
Y.lp.ui.NodeCaretPos.prototype.getCaretPos = function() {
    var elem = Y.Node.getDOMNode(this);
    if (elem.selectionEnd) {
        return elem.selectionEnd;
    } else if (document.selection) {
        var range = document.selection.createRange();
        if (range.parentElement() === elem) {
            var end_range = range.duplicate();
            end_range.moveStart("character", -elem.value.length);
            return end_range.text.length;
        }
    }
    return null;
};


}, "0.1", {"skinnable": true, "requires":["oop", "base", "event", "widget",
                                          "widget-stack", "node-menunav"]});
