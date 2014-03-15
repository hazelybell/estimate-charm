/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @namespace Y.lp.app.picker.team
 */

/*XXX jcsackett 08-27-2012 bug=1042831 This module and namespace should be
 * moved and renamed--it's not actually using the picker at all. It's an
 * overlay that I gets used in a picker in one circumstance.
 */
YUI.add('lp.app.picker.team', function(Y) {

var ns = Y.namespace('lp.app.picker.team');
ns.TEAM_CREATED = 'teamCreated';
ns.CANCEL_TEAM = 'cancelTeam';

ns.CreateTeamForm = Y.Base.create("createTeamWidget", Y.Base, [], {
    initializer: function(cfg) {
        this.publish(ns.TEAM_CREATED);
        this.publish(ns.CANCEL_TEAM);
        // We need to provide the 'New team' link functionality.
        // There could be several pickers and we only want to make the XHR
        // call to get the form once. So first one gets to do the call and
        // subsequent ones register the to be notified of the result.
        this.get('container').appendChild(this._get_template());
        this.error_handler =
            new Y.lp.client.FormErrorHandler({
                form: this.get('container')
            });
        var perform_load = false;
        if (!Y.Lang.isArray(ns.widgets)) {
            perform_load = true;
            ns.widgets = [];
        }
        ns.widgets.push(this);
        this._load_form(perform_load);
    },

    _get_template: function() {
        return [
          '<div id=form-placeholder ',
              'class="yui3-overlay-indicator-content">',
              '<img src="/@@/spinner-big/">',
          '</div>',
          '<div class="extra-form-buttons hidden">',
              '<button class="yes_button" type="submit" ',
              'name="field.actions.create" value="Create Team">',
              'Create Team</button>',
              '<button class="no_button" type="button">Cancel</button>',
            '</div>',
          '</div>'].join('');
    },

    _load_form: function (perform_load) {
        // Load the new team form from the model using an XHR call.
        // If perform_load is true, this is the first invocation of this method
        // across all pickers so we do the XHR call and send the result to all
        // registered pickers.
        // If perform_load is false, another picker is making the XNR call and
        // all we want to do is receive and render the preloaded_team_form.
        // We first check though that the result hasn't arrived already.
        if (Y.Lang.isValue(ns.team_form)) {
            this.render(ns.team_form, true);
            return;
        }
        if (!perform_load) {
            return;
        }

        var on_success = function(id, response) {
            ns.team_form = response.responseText;
            Y.Array.each(ns.widgets,
                function(widget) {
                    widget.render(ns.team_form, true);
                });
        };
        var on_failure = function(id, response) {
            Y.Array.each(ns.widgets,
                function(widget) {
                    widget.render(
                        'Sorry, an error occurred while loading the form.',
                        false);
            }   );
        };
        var cfg = {
            on: {success: on_success, failure: on_failure}
            };
        var uri = Y.lp.client.get_absolute_uri(
            'people/+simplenewteam/++form++');
        uri = uri.replace('api/devel', '');
        this.get("io_provider").io(uri, cfg);
    },

    render: function(form_html, show_submit) {
        // Poke the actual team form into the DOM and wire up the save and
        // cancel buttons.
        var container = this.get('container');
        container.one('#form-placeholder').replace(form_html);
        var submit_button = container.one(".yes_button");
        if (show_submit) {
            container.on('submit', function(e) {
                    e.halt();
                    this._save_new_team();
                }, this);
        } else {
            submit_button.addClass('hidden');
        }
        container.one(".no_button")
            .on('click', function(e) {
                e.halt();
                this.fire(ns.CANCEL_TEAM);
            }, this);
        this.membership_policy_edit = Y.lp.app.choice.addPopupChoice(
            'membership_policy', LP.cache.team_membership_policy_data, {
                container: container,
                render_immediately: false,
                field_title: 'membership policy'
            });
        container.one('.extra-form-buttons').removeClass('hidden');
    },

    show: function() {
        var form_elements = this.get('container').get('elements');
        if (form_elements.size() > 0) {
            form_elements.item(0).focus();
        }
        this.membership_policy_edit.render();
    },

    hide: function() {
        this.error_handler.clearFormErrors();
    },

    /**
     * Show the submit spinner.
     *
     * @method _showSpinner
     */
    _showSpinner: function(submit_link) {
        var spinner_node = Y.Node.create(
        '<img class="spinner" src="/@@/spinner" alt="Creating..." />');
        submit_link.insert(spinner_node, 'after');
    },

    /**
     * Hide the submit spinner.
     *
     * @method _hideSpinner
     */
    _hideSpinner: function(submit_link) {
        var spinner = submit_link.get('parentNode').one('.spinner');
        if (!Y.Lang.isNull(spinner)) {
            spinner.remove(true);
        }
    },

    _save_team_success: function(response, team_data) {
        var value = {
            "api_uri": "/~" + team_data['field.name'],
            "title": team_data['field.displayname'],
            "value": team_data['field.name'],
            "metadata": "team"};
        this.fire(ns.TEAM_CREATED, value);
        var container = this.get('container');
        container.all('button').detachAll();
        container.all('.spinner').remove(true);
        container.empty();
        container.appendChild(this._get_template());
        this.render(ns.team_form, true);
    },

    _save_new_team: function() {
        var that = this;
        var submit_link = Y.one("[name='field.actions.create']");
        this.error_handler.showError = function (error_msg) {
            that._hideSpinner(submit_link);
            that.error_handler.handleFormValidationError(error_msg, [], []);
            };
        var uri = Y.lp.client.get_absolute_uri('people/+simplenewteam');
        uri = uri.replace('api/devel', '');
        var form_data = {};
        var container = this.get('container');
        container.all("[name^='field.']").each(function(field) {
            form_data[field.get('name')] = field.get('value');
        });
        form_data.id = container;
        var y_config = {
            method: "POST",
            headers: {'Accept': 'application/json;'},
            on: {
                start: function() {
                    that.error_handler.clearFormErrors();
                    that._showSpinner(submit_link);
                },
                end: function () {
                    that._hideSpinner(submit_link);
                },
                failure: this.error_handler.getFailureHandler(),
                success: function (id, response, team_data) {
                    that._save_team_success(response, team_data);
                }
            },
            'arguments': form_data
        };
        y_config.form = form_data;
        this.get("io_provider").io(uri, y_config);
    }
}, {
    ATTRS: {
        /**
         * The form used to enter the new team details.
         */
        container: {
            valueFn: function() {return Y.Node.create('<form/>');}
        },
        /**
        * The object that provides the io function for doing XHR requests.
        *
        * @attribute io_provider
        * @type object
        * @default Y
        */
        io_provider: {value: Y}
    }
});


}, "0.1", {"requires": ["base", "node", "lp.app.choice"]});

