/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * A module to add support for watching and timing ajax events from the page.
 * Driven by the feature flag: visible_render_time.
 *
 * @module lp.ajax_log
 */
YUI.add('lp.ajax_log', function (Y) {

    var module = Y.namespace('lp');

    /**
     * Ajax log will watch ajax requests for timing information.
     *
     * @class ajax_log
     * @extends Y.Base
     * @namespace Y.lp
     *
     */
    module.ajax_log = Y.Base.create('ajax_log', Y.Base, [], {
        _bind_events: function () {
            var that = this;
            var node = Y.one('#ajax-time-list');
            var ajax_request_times = {};
            var ajax_menu_animating = false;
            var flash_menu = Y.lp.anim.green_flash({node:'#ajax-time'});

            // Open/close the log.
            Y.on('click', function(e) {
                e.halt();
                Y.one('#ajax-time-list').toggleClass('hidden');
            }, '#ajax-time a');

            flash_menu.on('end', function() {
                ajax_menu_animating = false;
            });

            /* When an AJAX event starts, record the time.
            */
            Y.on('io:start', function(transactionid) {
                var now = new Date();
                ajax_request_times[transactionid] = now;
            });

            /* When an AJAX event finishes add it to the log.
            */
            Y.on('io:complete', function(transactionid, response) {
                /* The AJAX event has finished so record the time.
                */
                var finish_time = new Date();
                /* Remove the initial message in the log.
                */
                Y.all('#ajax-time-list li.no-events').remove();
                if (ajax_request_times[transactionid]) {
                    var oops_url = 'https://oops.canonical.com/oops/?oopsid=';
                    var start_time = ajax_request_times[transactionid];
                    /* The time take for the AJAX event, in seconds.
                    */
                    var time_taken = (finish_time - start_time)/1000;
                    var log_node = Y.Node.create(
                        '<li>Time: <strong></strong><span></span></li>');
                    log_node.addClass('transaction-' + transactionid);
                    log_node.one('strong').set(
                        'text', time_taken.toFixed(2) + ' seconds');

                    // if the AJAX event takes longer than ajax_ok_time
                    // then add a warning.
                    if (time_taken > that.get('ajax_ok_time')) {
                        log_node.one('strong').addClass('warning');
                    }
                    log_node.one('span').set(
                            'text',
                            'ID: ' + transactionid +
                            ', status: ' + response.status +
                            ' (' + response.statusText + ')');
                    var oops = response.getResponseHeader('X-Lazr-OopsId');
                    if (oops) {
                        var oops_node = Y.Node.create('<a/>');
                        oops_node.setAttribute('href', oops_url + oops);
                        oops_node.set('text', oops);
                        log_node.one('span').append(', OOPS ID:&nbsp;');
                        log_node.one('span').append(oops_node);
                    }
                    node.prepend(log_node);

                    // Highlight the new entry in the log.
                    Y.lp.anim.green_flash({
                        node: '#ajax-time-list li.transaction-'+transactionid
                    }).run();

                    // Signify a new entry has been added to the log.
                    if (ajax_menu_animating === false) {
                        flash_menu.run();
                        ajax_menu_animating = true;
                    }
                }
            });
        },

        /**
         * Basic initializer to build the events for the instance.
         *
         * @method intializer
         * @param {Object} cfg
         *
         */
        initializer: function (cfg) {
            var that = this;
            Y.on('contentready', function() {
                that._bind_events();
            }, '#ajax-time');
        }
    }, {
        ATTRS: {
            /**
             * Requests slower than this are marked as slow. Value in seconds.
             *
             * @attribute ajax_ok_time
             * @default 1
             * @type Integer
             *
             */
            ajax_ok_time: {
                value: 1
            }
        }
    });
}, '0.1', {
    'requires': ['node', 'lp.anim']
});
