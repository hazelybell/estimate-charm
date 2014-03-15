/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide functionality for picking a bug.
 *
 * @module bugs
 * @submodule bug_picker
 */
YUI.add('lp.bugs.bug_picker', function(Y) {

var namespace = Y.namespace('lp.bugs.bug_picker');

/**
 * A widget to allow a user to choose a bug.
 * This widget does no rendering itself; it is used to enhance existing HTML.
 */
namespace.BugPicker = Y.Base.create(
        "bugPickerWidget", Y.lp.ui.picker.Picker, [], {
    initializer: function(cfg) {
        this.io_provider = Y.lp.client.get_configured_io_provider(cfg);
        var that = this;
        this.after('search', function(e) {
            var bug_id = e.details[0];
            that._find_bug({id: bug_id});
        });
    },

    _save_button_html: function() {
        return [
            '<button type="button" name="field.actions.save">',
            this.get('save_link_text'),
            '</button>'].join('');
    },

    _remove_link_html: function() {
        return [
            '<div class="centered">',
            '<a class="sprite remove ',
            'js-action" href="javascript:void(0)">',
            this.get('remove_link_text'),
            '</a></div>'].join('');
    },

    hide: function() {
        this.get('boundingBox').setStyle('display', 'none');
        Y.lp.ui.picker.Picker.prototype.hide.call(this);
    },

    show: function() {
        this.get('boundingBox').setStyle('display', 'block');
        Y.lp.ui.picker.Picker.prototype.show.call(this);
    },

    _bug_search_header: function() {
        return this._remove_link_html();
    },

    // Centre the picker along the x axis without changing y position.
    _xaxis_centre: function() {
        var viewport = Y.DOM.viewportRegion();
        var new_x = (viewport.right  + viewport.left)/2 -
            this.get('contentBox').get('offsetWidth')/2;
        this.move([new_x, this._getY()]);

    },

    renderUI: function() {
        Y.lp.ui.picker.Picker.prototype.renderUI.apply(this, arguments);
        var search_header = Y.Node.create(this._bug_search_header());
        var search_node = this._search_input.get('parentNode');
        search_node.insert(search_header, 'before');
        this.remove_link = search_node.get('parentNode').one('a.remove');
    },

    bindUI: function() {
        Y.lp.ui.picker.Picker.prototype.bindUI.apply(this, arguments);
        // Wire up the Remove link.
        var that = this;
        if (Y.Lang.isValue(this.remove_link)) {
            this.remove_link.on('click', function(e) {
                e.halt();
                that.fire(namespace.BugPicker.REMOVE);
            });
        }
        this.after('visibleChange', function() {
            if (!this.get('visible')) {
                that._hide_bug_results();
            } else {
                if (Y.Lang.isValue(that.remove_link)
                        && that.get('remove_link_visible')) {
                    that.remove_link.removeClass('hidden');
                } else {
                    that.remove_link.addClass('hidden');
                }
            }
        });
    },

    /**
     * Show a spinner for the specified node.
     *
     * @method _show_bug_spinner
     * @param node
     * @protected
     */
    _show_bug_spinner: function(node) {
        if( Y.Lang.isValue(node)) {
            node.addClass('update-in-progress-message');
            node.set('disabled', true);
        }
    },

    /**
     * Hide the spinner for the specified node.
     * @param node
     * @protected
     */
    _hide_bug_spinner: function(node) {
        if( Y.Lang.isValue(node)) {
            node.removeClass('update-in-progress-message');
            node.set('disabled', false);
        }
    },

    /**
     * Look up the selected bug and get the user to confirm that it is the one
     * they want.
     *
     * @param data
     * @protected
     */
    _find_bug: function(data) {
        var bug_id = Y.Lang.trim(data.id);
        var qs_data
            = Y.lp.client.append_qs("", "ws.accept", "application.json");
        qs_data = Y.lp.client.append_qs(qs_data, "ws.op", "getBugData");
        qs_data = Y.lp.client.append_qs(qs_data, "bug_id", bug_id);
        if (Y.Lang.isValue(LP.cache.bug)) {
            qs_data = Y.lp.client.append_qs(
                qs_data, "related_bug", LP.cache.bug.self_link);
        }
        var that = this;
        var config = {
            on: {
                end: function() {
                    that.set('search_mode', false);
                },
                success: function(id, response) {
                    if (response.responseText === '') {
                        return;
                    }
                    var bug_data = Y.JSON.parse(response.responseText);
                    if (!Y.Lang.isArray(bug_data) || bug_data.length === 0) {
                        var error_msg =
                            bug_id + ' is not a valid bug number.';
                        that._hide_bug_results();
                        that.set('error', error_msg);
                        return;
                    }
                    that.set('results', bug_data);
                },
                failure: function(id, response) {
                    that._hide_bug_results();
                    that.set('error', response.responseText);
                }
            },
            data: qs_data
        };
        var uri
            = Y.lp.client.get_absolute_uri("/api/devel/bugs");
        this.io_provider.io(uri, config);
    },

    // Template for rendering the bug details.
    _bug_details_template: function() {
        return [
        '<table class="confirm-bug-details"><tbody><tr><td>',
        '<div id="client-listing">',
        '  <div class="buglisting-col1">',
        '      <div class="importance {{importance_class}}">',
        '          {{importance}}',
        '      </div>',
        '      <div class="status {{status_class}}">',
        '          {{status}}',
        '      </div>',
        '      <div class="buginfo-extra">',
        '              <div class="information_type">',
        '                  {{information_type}}',
        '              </div>',
        '      </div>',
        '  </div>',
        '  <div class="buglisting-col2">',
        '  <a href="{{bug_url}}" class="bugtitle sprite new-window" ',
        '  style="padding-top: 3px">',
        '  <p class="ellipsis single-line">',
        '  <span class="bugnumber">#{{id}}</span>',
        '  &nbsp;{{bug_summary}}</p></a>',
        '  <div class="buginfo-extra">',
        '      <p class="ellipsis single-line">{{description}}</p></div>',
        '  </div>',
        '</div></td></tr>',
        '{{> private_warning}}',
        '</tbody></table>'
        ].join(' ');
    },

    _private_warning_template: function(message) {
        return [
        '{{#private_warning}}',
        '<tr><td><p id="privacy-warning" ',
        'class="block-sprite large-warning">',
        message,
        '</p></td></tr>',
        '{{/private_warning}}'
        ].join(' ');
    },

    // Template for the bug confirmation form.
    _bug_confirmation_form_template: function() {
        return [
            '<div class="bug-details-node" ',
            'style="margin-top: 6px;">',
            '{{> bug_details}}',
            '</div>'].join('');
    },

    _syncResultsUI: function() {
        var bug_data = this.get('results');
        if (!bug_data.length) {
            this._hide_bug_results();
            return;
        }
        // The server may return multiple bugs but for now we only
        // support displaying one of them.
        bug_data = bug_data[0];
        bug_data.private_warning
            = this.get('public_context') && bug_data.is_private;
        var private_warning_message
            = this.get('private_warning_message');
        var html = Y.lp.mustache.to_html(
            this._bug_confirmation_form_template(),
            bug_data, {
                bug_details: this._bug_details_template(),
                private_warning:
                    this._private_warning_template(private_warning_message)
        });
        var bug_details_node = Y.Node.create(html);
        var bug_link = bug_details_node.one('.bugtitle');
        bug_link.on('click', function(e) {
            e.halt();
            window.open(bug_link.get('href'));
        });
        this._show_bug_results(bug_details_node);
        var that = this;
        this.save_button
            .on('click', function(e) {
                e.halt();
                that.fire(namespace.BugPicker.SAVE, bug_data);
            });
    },

    /** Show the results of a bug search.
     * @method _show_bug_details_node
     * @protected
     */
    _show_bug_results: function(new_bug_details_node) {
        this._results_box.empty(true);
        this._results_box.appendChild(new_bug_details_node);
        if (!Y.Lang.isValue(this.save_button)) {
            this.save_button = Y.Node.create(this._save_button_html());
            this.set('footer_slot', this.save_button);
        } else {
            this.save_button.detachAll();
        }
        this.save_button.focus();
        this._xaxis_centre();
        var use_animation = this.get('use_animation');
        if (!use_animation) {
            this.bug_details_node = new_bug_details_node;
            return;
        }
        new_bug_details_node.addClass('transparent');
        new_bug_details_node.setStyle('opacity', 0);
        var fade_in = new Y.Anim({
            node: new_bug_details_node,
            to: {opacity: 1},
            duration: 0.8
        });
        var that = this;
        fade_in.on('end', function() {
            that.bug_details_node = new_bug_details_node;
        });
        fade_in.run();
    },

    /** Hide the results of a bug search.
     * @method _hide_bug_results
     * @protected
     */
    _hide_bug_results: function() {
        if(Y.Lang.isValue(this.bug_details_node)) {
            this._results_box.empty(true);
        }
        this.set('error', null);
        this.bug_details_node = null;
        if (Y.Lang.isValue(this.save_button)) {
            this.save_button.detachAll();
            this.save_button.remove(true);
            this.save_button = null;
        }
        this._xaxis_centre();
    }
}, {
    ATTRS: {
        // Is the context in which this form being used public.
        public_context: {
            getter: function() {
                return !Y.one(document.body).hasClass('private');
            }
        },
        // Warning to display if we select a private bug from a public context.
        private_warning_message: {
            value: 'You are selecting a private bug.'
        },
        // The text used for the remove link.
        save_link_text: {
            value: "Save bug"
        },
        // The text used for the remove link.
        remove_link_text: {
            value: "Remove bug"
        },
        remove_link_visible: {
            value: false
        },
        // Override for testing.
        use_animation: {
            value: true
        },

        // The following attributes override the default picker values.
        align: {
            value: {
                points: [Y.WidgetPositionAlign.CC,
                         Y.WidgetPositionAlign.CC]
            }
        },
        progressbar: {
            value: true
        },
        progress: {
            value: 0
        },
        header_text: {
           value: 'Select a bug'
        },
        headerContent: {
            getter: function() {
                return Y.Node.create("<h2></h2>").set('text',
                    this.get('header_text'));
            }
        },
        search_text_too_short_message: {
            getter: function() {
                return 'Please enter a valid bug number.';
            }
        },
        min_search_chars: {
            value: 1
        },
        clear_on_cancel: {
            value: true
        }
    }
});

// Events
namespace.BugPicker.SAVE = 'save';
namespace.BugPicker.REMOVE = 'remove';

}, "0.1", {"requires": [
    "base", "io", "oop", "node", "event", "json",
    "lp.ui.effects", "lp.mustache", "lp.ui.picker-base"]});
