/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Support the UI for registering a new project.
 *
 * @module views.registry
 * @requires base, node, effects, lp.app.choice
 */
YUI.add('registry.product-views', function (Y) {
    var ns = Y.namespace('registry.views');
    var info_type = Y.lp.app.information_type;
    var COMMERCIAL_LICENSE = "OTHER_PROPRIETARY";

    /**
     * Handle binding up events for our information type choice widget.
     *
     * @function bind_information_type
     * @param {View} view
     * @param {String} value
     */
    var bind_information_type = function (view) {
        var widget = Y.lp.app.choice.addPopupChoiceForRadioButtons(
            'information_type',
            info_type.cache_to_choicesource(
                LP.cache.information_type_data));

        // We are not doing ajax saves of the information type so we need to
        // disable the flash on save for the widget.
        widget.set('flashEnabled', false);

        // When the information type changes, check if we should show/hide
        // UI components.
        widget.on('save', function (ev) {
            view.information_type_change(ev.target.get('value'));
        });

        // If we don't have a value to start with, always default to PUBLIC.
        if (widget.get('value')) {
            view.information_type_change(widget.get('value'));
        } else {
            view.information_type_change('PUBLIC');
        }

        // Hold onto the reference to the information type widget so we
        // can test with it.
        view._information_type_widget = widget;
    };

    /**
     * Update the visiblity and settings of the license field based on the
     * value of the information type.
     *
     * @function toggle_license_field
     * @param {String} value of the information type
     *
     */
    var toggle_license_field = function (value) {
        // The license code is nested in another table.
        var license = Y.one('input[name="field.licenses"]');
        var license_cont = license.ancestor('td').ancestor('td');

        if (info_type.get_cache_data_from_key(value, 'value',
                                              'is_private')) {
            // Hide the license field and set it to commercial.
            license_cont.hide();

            // We have to set both checked and the value because value is
            // a DOM object property, but the UI is updated based on the
            // 'checked' attribute.
            var commercial = 'input[value="' + COMMERCIAL_LICENSE + '"]';
            Y.one(commercial).set('checked', 'checked');
            license.set('value', COMMERCIAL_LICENSE);
            Y.one('textarea[name="field.license_info"]').set(
                'value', 'Launchpad 30-day trial commercial license');
        } else {
            // Show the license field.
            license_cont.show();
        }
    };


    /**
     * View handler for the Project Edit view.
     *
     * @class registry.views.EditProduct
     * @extends Y.View
     *
     */
    ns.EditProduct = Y.Base.create('edit-project-view', Y.View, [], {
        /**
         * Update the UI when the information type changes.
         *
         * @method _information_type_change
         * @param {String} information_type value
         */
        information_type_change: function (value) {
            toggle_license_field(value);
            Y.fire(info_type.EV_CHANGE, {
                value: value
            });
        },

        /**
         * Render out the View into the active page.
         *
         * @method render
         */
        render: function (information_type_value) {
            // Only bind the information type if it's available due to the
            // feature flag.
            if (Y.one('input[name="field.information_type"]')) {
                // get the original value, if there is one set.
                bind_information_type(this);
            }
        }
    }, {
        ATTRS: {
            container: {
                value: '.yui-main'
            }
        }
    });

    /**
     * Handle setting up the JS for the new project View
     *
     * @class registry.views.NewProduct
     * @extends Y.Base
     */
    ns.NewProduct = Y.Base.create('new-product-view', Y.Base, [], {
        // These two regexps serve slightly different purposes.  The first
        // finds the leftmost run of valid url characters for the autofill
        // operation.  The second validates the entire string, used for
        // explicit entry into the URL field.  These are simple enough to keep
        // in sync so it doesn't bother me that we repeat most of it.  Note
        // that while both ignore case, only the first one should be global in
        // order to utilize the RegExp.lastIndex behavior of .exec().
        valid_urls: new RegExp('^[a-z0-9][-.+a-z0-9]*', 'ig'),
        valid_char: new RegExp('^[a-z0-9][-.+a-z0-9]*$', 'i'),

        /**
         * Bind the url/name field interaction
         *
         * @method _bind_name_field
         * @private
         */
        _bind_name_field: function () {
            var url_field = Y.one('input[id="field.name"]');
            var name_field = Y.one('input[id="field.displayname"]');
            name_field.on('keyup', this._url_autofill, this);

            // Explicitly typing into the URL field disables autofilling.
            url_field.on('keyup', function(e) {
                if (url_field.get('value') === '') {
                    // The user cleared the URL field; turn on autofill.
                    name_field.on('keyup', this._url_autofill);
                } else {
                    /* Honor the user's URL; turn off autofill. */
                    name_field.detach('keyup', this._url_autofill);
                }
            }, this);

            // Prevent invalid characters from being input into the URL field.
            url_field.on('keypress', function(e) {
                // Handling key events is madness.  For a glimpse, see
                // http://unixpapa.com/js/key.html
                //
                // Additional spice for the insanity stew is given by the
                // rhino book, page 428.  This code is basically a rip and
                // remix of those two texts.
                var event = e || window.event;
                var code = e.charCode || e.keyCode;

                if (/* Check for special characters. */
                    e.which === 0 || e.which === null ||
                    /* Check for function keys (Firefox only). */
                    e.charCode === 0 ||
                    /* Check for ctrl or alt held down. */
                    e.ctrlKey || e.altKey ||
                    /* Check for ASCII control character */
                    32 > code)
                {
                    return true;
                }
                var char = String.fromCharCode(code);
                var new_value = url_field.get('value') + char;
                if (new_value.search(this.valid_char) >= 0) {
                    /* The character is valid. */
                    return true;
                }
                e.preventDefault();
                e.returnValue = false;
                return false;
            }, this);
        },

        /**
         * When the 'No' button is clicked, we swap in the registration
         * details for the search results.  It really doesn't look good
         * to leave the search results there.
         *
         * @method _complete_registration
         * @param {Event}
         * @private
         */
        _complete_registration: function(ev) {
            var that = this;
            ev.halt();
            var step_title = Y.one('#step-title');
            var expander = Y.one('#search-results-expander');

            /* Slide in the search results and hide them under a link. */
            expander.removeClass('hidden');
            expander.on('click', function(e) {
                e.halt();

                var arrow = Y.one('#search-results-arrow');
                if (arrow.getAttribute('src') === '/@@/treeCollapsed') {
                    // The search results are currently hidden.  Slide them
                    // out and turn the arrow to point downward.
                    arrow.setAttribute('src', '/@@/treeExpanded');
                    arrow.setAttribute('title', 'Hide search results');
                    arrow.setAttribute('alt', 'Hide search results');
                    Y.lp.ui.effects.slide_out(that.get('search_results')).run();
                    that._show_separator(true);
                }
                else {
                    // The search results are currently displayed.  Slide them
                    // in and turn the arrow to point rightward.
                    arrow.setAttribute('src', '/@@/treeCollapsed');
                    arrow.setAttribute('title', 'Show search results');
                    arrow.setAttribute('alt', 'Show search results');
                    Y.lp.ui.effects.slide_in(that.get('search_results')).run();
                    that._show_separator(false);
                }
           }, this);

           // Hide the 'No' button, but slide out the search results, so the
           // user has a clue that Something Is Happening.
           this.get('details_buttons').addClass('hidden');

           // Slide out the registration details widgets, but add an 'end'
           // event handler so that the height style left by lp.ui.effects is
           // removed when the animation is done.  We're never going to slide
           // the form widgets back in, and the height style causes the
           // licence widget to dive under the Complete Registration button.
           // See bug 391138 for details.
           var anim = Y.lp.ui.effects.slide_out(this.get('form_widgets'));
           anim.on('end', function() {
               that.get('form_widgets').setStyle('height', null);
           });
           anim.run();

           // Toggle the visibility of the various other widgets.
           this.get('form_actions').removeClass('hidden');
           this.get('title').removeClass('hidden');

           // Set the H2 title to something more appropriate for the
           // selected task.
           step_title.set('innerHTML', 'Step 2 (of 2) Registration details');

           var reset_height = this.get('search_results').getComputedStyle(
                'height');
           this.get('search_results').setStyle('height', reset_height);
           Y.lp.ui.effects.slide_in(this.get('search_results')).run();

           // Append a special marker to the hidden state widget. See
           // ProjectAddStepTwo.search_results_count() for details.
           var steps = this.get('marker').getAttribute('value');
           if (0 > steps.search(new RegExp('hidesearch'))) {
               this.get('marker').setAttribute('value', steps + "|hidesearch");
           }
        },

        /**
         * Handle the reveals when there are search results.
         *
         * @method _show_separator
         * @param {Boolean}
         * @private
         */
        _show_separator: function (flag) {
            var separator = Y.one('#registration-separator');
            if (!separator) {
                // The separator is not on the page, because there were no
                // search results.
                return;
            }
            if (flag) {
                separator.removeClass('hidden');
            } else {
                separator.addClass('hidden');
            }
        },

        /**
         * Generate a url for the project based on the name.
         *
         * @method _url_autofill
         * @param {Event}
         * @private
         */
        _url_autofill: function (e) {
            var url_field = Y.one('input[id="field.name"]');
            var name_value = e.target.get('value');
            if (name_value === '') {
                /* When Name is empty, clear URL. */
                url_field.set('value', '');
            } else {
                // Fill the URL field with as much of the left part of the
                // string as matches the regexp.  If the regexp doesn't
                // match (say because there's illegal stuff at the front),
                // don't change the current URL field.  We have to reset
                // lastIndex each time we get here so that search begins
                // at the front of the string.
                this.valid_urls.lastIndex = 0;
                var match = this.valid_urls.exec(name_value);
                if (match) {
                    var slice = name_value.slice(0, this.valid_urls.lastIndex);
                    url_field.set('value', slice);
                }
            }
        },

        /**
         * Bind the UI interactions that will be tracked through the View
         * lifecycle.
         *
         * @method bindUI
         */
        bindUI: function () {
            if (Y.one('input[name="field.information_type"]')) {
                bind_information_type(this);
            }

            if(Y.one('input[id="field.name"]')) {
                this._bind_name_field();
            }

            if (this.get('details_buttons')) {
                this.get('details_buttons').on('click',
                                               this._complete_registration,
                                               this);
            }
        },

        /**
         * Update the UI when the information type changes.
         *
         * @method _information_type_change
         * @param {String} information_type value
         */
        information_type_change: function (value) {
            toggle_license_field(value);
            Y.fire(info_type.EV_CHANGE, {
                value: value
            });
            var driver_cont =
                Y.one('input[name="field.driver"]').ancestor('td');
            var bug_super_cont =
                Y.one('input[name="field.bug_supervisor"]').ancestor('td');

            if (info_type.get_cache_data_from_key(value, 'value',
                                                  'is_private')) {
                // Hide the driver and bug supervisor fields.
                driver_cont.show();
                bug_super_cont.show();
            } else {
                driver_cont.hide();
                bug_super_cont.hide();
            }
        },

        /**
         * Standard YUI init.
         *
         * @method initialize
         * @param {Object}
         */
        initialize: function (cfg) {
            // The details button is only visible when JavaScript is enabled,
            // but the H3 separator is only visible when JavaScript is
            // disabled.  Neither is displayed on the step 1 page.
            this._show_separator(false);
        },

        /**
         * Render the view by binding to the current DOM.
         *
         * @method render
         */
        render: function () {
            this.bindUI();

            if (this.get('details_buttons')) {
                this.get('details_buttons').removeClass('hidden');
            }

            // If there are search results, hide the registration details.
            if (this.get('search_results')) {
                this.get('form_widgets').addClass('hidden');
                this.get('form_actions').addClass('hidden');
                this.get('title').addClass('hidden');
            }

            // If we've been here before (e.g. there was an error in
            // submitting step 2), jump to continuing the registration.
            var marker = this.get('marker');
            if (marker &&
                marker.getAttribute('value').search(/hidesearch/) >= 0) {
                this._complete_registration(null);
            }
        }
    }, {
        ATTRS: {
            /**
             * Lazy load the found node for use through out the View.
             *
             * @attribute details_buttons
             * @default Node
             * @type Node
             */
            details_buttons: {
                valueFn: function (val) {
                    return Y.one('#registration-details-buttons');
                }
            },

            /**
             * Lazy load the found node for use through out the View.
             *
             * @attribute form_actions
             * @default Node
             * @type Node
             */
            form_actions: {
                valueFn: function (va) {
                    return Y.one('#launchpad-form-actions');
                }
            },

            /**
             * Lazy load the found node for use through out the View.
             *
             * @attribute form_widgets
             * @default Node
             * @type Node
             */
            form_widgets: {
                valueFn: function (val) {
                    return Y.one('#launchpad-form-widgets');
                }
            },

            /**
             * Lazy load the found node for use through out the View.
             * This is the magic hidden widget used by the MultiStepView.
             *
             * @attribute marker
             * @default Node
             * @type Node
             */
            marker: {
                valueFn: function (val) {
                    return Y.one(Y.DOM.byId('field.__visited_steps__'));
                }
            },

            /**
             * Lazy load the found node for use through out the View.
             *
             * @attribute search_results
             * @default Node
             * @type Node
             */
            search_results: {
                valueFn: function (val) {
                    return Y.one('#search-results');
                }
            },

            /**
             * Lazy load the found node for use through out the View.
             *
             * @attribute title
             * @default Node
             * @type Node
             */
            title: {
                valueFn: function (val) {
                    return Y.one('#registration-details-title');
                }
            }
        }
    });

}, '0.1', {
    'requires': ['base', 'node', 'view', 'lp.ui.effects', 'lp.app.choice',
                 'lp.ui.choiceedit', 'lp.app.information_type']
});
