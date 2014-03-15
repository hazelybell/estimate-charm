/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @namespace Y.lp.app.picker
 * @requires lp.ui.picker-base
 */
YUI.add('lp.ui.picker-person', function(Y) {

var ns = Y.namespace('lp.ui.picker');
/*
 * Extend the picker into the PersonPicker
 */

ns.PersonPicker = Y.Base.create('picker', Y.lp.ui.picker.Picker, [], {

    initializer: function(cfg) {
        // If the user isn't logged in, override the show_assign_me value.
        if (!Y.Lang.isValue(LP.links.me)) {
            this.set('show_assign_me_button', false);
        }
        if (this.get('show_create_team')) {
            // We need to provide the 'New team' link.
            // Set up the widget to provide the form.
            var ctns = Y.lp.app.picker.team;
            this.new_team_widget = new ctns.CreateTeamForm({
                io_provider: cfg.io_provider
            });
            this.new_team_widget.subscribe(
                ctns.CANCEL_TEAM, function(e) {
                    this.hide_new_team_form();
                }, this);
            this.new_team_widget.subscribe(
                ctns.TEAM_CREATED, function(e) {
                    this.fire('save', e.details[0]);
                }, this);
        }
    },

    hide: function() {
        this.get('boundingBox').setStyle('display', 'none');
        // We want to cancel the new team form is there is one rendered.
        if (Y.Lang.isValue(this.new_team_widget)) {
            this.new_team_widget.hide();
            this.hide_extra_content(
                this.new_team_widget.get('container'), false);
        }

        Y.lp.ui.picker.Picker.prototype.hide.call(this);
    },

    show: function() {
        this.get('boundingBox').setStyle('display', 'block');
        Y.lp.ui.picker.Picker.prototype.show.call(this);
    },

    _update_button_text: function() {
        var link_text;
        if (this.get('selected_value_metadata') === 'team') {
            link_text = this.get('remove_team_text');
        } else {
            link_text = this.get('remove_person_text');
        }
        this.remove_button.set('text', link_text);
    },

    _show_hide_buttons: function () {
        var selected_value = this.get('selected_value');
        if (this.remove_button) {
            if (selected_value === null) {
                this.remove_button.addClass('yui3-picker-hidden');
            } else {
                this.remove_button.removeClass('yui3-picker-hidden');
                this._update_button_text();
            }
        }

        if (this.assign_me_button) {
            if (LP.links.me.match('~' + selected_value + "$") ||
                LP.links.me === selected_value) {
                this.assign_me_button.addClass('yui3-picker-hidden');
            } else {
                this.assign_me_button.removeClass('yui3-picker-hidden');
            }
        }
    },

    remove: function () {
        this.hide();
        this.fire('save', {value: null});
    },

    assign_me: function () {
        var name = LP.links.me.replace('/~', '');
        this.fire('save', {
            image: '/@@/person',
            title: 'Me',
            api_uri: LP.links.me,
            value: name
        });
    },

    show_new_team_form: function() {
        var form = this.new_team_widget.get('container');
        this.show_extra_content(form, "Enter new team details");
        this.new_team_widget.show();
        this.set('centered', true);
    },

    hide_new_team_form: function() {
        this.new_team_widget.hide();
        var form = this.new_team_widget.get('container');
        this.hide_extra_content(form);
        this.set('centered', true);
    },

    _assign_me_button_html: function() {
        return [
            '<a class="yui-picker-assign-me-button sprite person ',
            'js-action" href="javascript:void(0)" ',
            'style="padding-right: 1em">',
            this.get('assign_me_text'),
            '</a>'].join('');
    },

    _remove_button_html: function() {
        return [
            '<a class="yui-picker-remove-button sprite remove ',
            'js-action" href="javascript:void(0)" ',
            'style="padding-right: 1em">',
            this.get('remove_person_text'),
            '</a>'].join('');
    },

    _new_team_button_html: function() {
        return [
            '<a class="yui-picker-new-team-button sprite add ',
            'js-action" href="javascript:void(0)">',
            'New Team',
            '</a>'].join('');
    },
    renderUI: function() {
        Y.lp.ui.picker.Picker.prototype.renderUI.apply(this, arguments);
        var extra_buttons = this.get('extra_buttons');
        var remove_button, assign_me_button, new_team_button;

        if (this.get('show_remove_button')) {
            remove_button = Y.Node.create(this._remove_button_html());
            remove_button.on('click', this.remove, this);
            extra_buttons.appendChild(remove_button);
            this.remove_button = remove_button;
        }

        if (this.get('show_assign_me_button')) {
            assign_me_button = Y.Node.create(this._assign_me_button_html());
            assign_me_button.on('click', this.assign_me, this);
            extra_buttons.appendChild(assign_me_button);
            this.assign_me_button = assign_me_button;
        }
        if (this.get('show_create_team')) {
            new_team_button = Y.Node.create(this._new_team_button_html());
            new_team_button.on('click', this.show_new_team_form, this);
            extra_buttons.appendChild(new_team_button);
        }
        this._search_input.insert(
            extra_buttons, this._search_input.get('parentNode'));
        this._show_hide_buttons();
        this.after("selected_valueChange", function(e) {
            this._show_hide_buttons();
        });
    }
}, {
    ATTRS: {
        extra_buttons: {
            valueFn: function () {
                return Y.Node.create('<div class="extra-form-buttons"/>');
            }
        },
        show_assign_me_button: { value: true },
        show_remove_button: {value: true },
        assign_me_text: {value: 'Pick me'},
        remove_person_text: {value: 'Remove person'},
        remove_team_text: {value: 'Remove team'},
        min_search_chars: {value: 2},
        show_create_team: {value: false}
    }
});
}, "0.1", {"requires": [
    "base", "node", "lp.ui.picker-base", "lp.app.picker.team"]});
