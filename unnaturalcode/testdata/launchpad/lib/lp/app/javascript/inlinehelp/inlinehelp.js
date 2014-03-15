/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.app.inlinehelp
 *
 * Usage:
 *      lp.app.inlinehelp.init_help();
 *
 */
YUI.add('lp.app.inlinehelp', function (Y) {

    var module = Y.namespace('lp.app.inlinehelp');
    var HELP_LINK_SELECTOR = 'a[target=help]';
    var HELP_CSS = 'help';
    var CLICK_DELEGATE = false;

    /**
     * Handle the clicking of a help link in the body.
     * This is a delegated handler so this == the object clicked.
     *
     * @method _show_help
     * @private
     */
    module._show_help = function (e) {
        e.preventDefault();
        var target_link = e.currentTarget;

        // init the overlay and show it
        var overlay = new module.InlineHelpOverlay({
            'contentUrl': target_link.get('href'),
            'centered': true,
            'constrain': true,
            // we need our help overlay to have a higher zindex than usual
            // overlays so that any help on them appear above them
            'zIndex': 1050
        });
        overlay.render();
    };

    /**
     * The single entry point used to bind the buttons for launching help.
     *
     * @method init_help
     * @public
     */
    module.init_help =  function () {
        // Find the help links.
        var links = Y.all(HELP_LINK_SELECTOR);

        // Add the help class.
        links.addClass(HELP_CSS);

        // Bind the click events but unbind it first in case we're re-running
        // init more than once (say on ajax loading of new help content).
        var body = Y.one('body');
        if (CLICK_DELEGATE !== false) {
            CLICK_DELEGATE.detach();
        }
        CLICK_DELEGATE = body.delegate(
            'click',
            module._show_help,
            HELP_LINK_SELECTOR
        );
    };

    module.InlineHelpOverlay = Y.Base.create(
        'inlinehelp-overlay',
        Y.lp.ui.PrettyOverlay,
        [],
        {
            /**
             * Generate the iframe used for displaying help content in the
             * overlay.
             *
             * @method _getContent
             * @private
             */
            _getContent: function () {
                var help_page = Y.Node.create('<iframe/>');
                help_page.set('src', this.get('contentUrl'));

                // Use the overlay bodyContent as the home of the iframe.
                this.set('bodyContent', help_page);
            },

            initializer: function (cfg) {
                this._getContent();
            },

            hide: function() {
                this.constructor.superclass.hide.call(this);
                this.get('boundingBox').setStyle('display', 'none');
            },

            show: function() {
                this.constructor.superclass.show.call(this);
                this.get('boundingBox').setStyle('display', 'block');
            }
        },
        {
            ATTRS: {
                /**
                 * URI of the location of the help content.
                 *
                 * This is loaded into our iFrame and should be a full page vs
                 * a data payload.
                 *
                 * @attribute contentUrl
                 * @type string
                 * @default ''
                 */
                contentUrl: {
                    value: ''
                },

                /**
                 * There's no multi steps so hard code the underlying overlays
                 * bar to false.
                 *
                 * @attribute progressbar
                 * @type bool
                 * @default false
                 */
                progressbar: {
                    value: false
                }
            }
        }
    );

}, "0.1", { "requires": ['lp.ui.overlay', 'io'] });
