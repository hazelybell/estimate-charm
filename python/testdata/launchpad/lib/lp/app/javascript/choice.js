YUI.add('lp.app.choice', function(Y) {

var namespace = Y.namespace('lp.app.choice');

namespace.hook_up_choicesource_spinner = function(widget) {
  // ChoiceSource makes assumptions about HTML in lazr-js
  // that don't hold true here, so we need to do our own
  // spinner icon and clear it when finished.
  Y.after(function() {
    var icon = this.get('editicon');
    icon.removeClass('edit');
    icon.addClass('update-in-progress-message');
    icon.setStyle('position', 'relative');
    icon.setStyle('bottom', '2px');
  }, widget, '_uiSetWaiting');
  Y.after(function() {
    var icon = this.get('editicon');
    icon.removeClass('update-in-progress-message');
    icon.addClass('edit');
    icon.setStyle('bottom', '0px');
  }, widget, '_uiClearWaiting');
};

namespace.addBinaryChoice = function(config, resource_uri, attribute) {
  var widget = new Y.ChoiceSource(config);
  widget.plug({
    fn: Y.lp.client.plugins.PATCHPlugin,
    cfg: {
      patch: attribute,
      resource: resource_uri}});
  namespace.hook_up_choicesource_spinner(widget);
  widget.render();
};


namespace.addEnumChoice = function(config, resource_uri, attribute) {

  var widget = new Y.ChoiceSource(config);
  widget.plug({
    fn: Y.lp.client.plugins.PATCHPlugin,
    cfg: {
      patch: attribute,
      resource: resource_uri}});
  namespace.hook_up_choicesource_spinner(widget);
  widget.on('save', function(e) {
      var cb = widget.get('contentBox');
      var value = widget.get('value');
      Y.Array.each(config.items, function(item) {
          if (item.value === value) {
            cb.one('span').addClass(item.css_class);
          } else {
            cb.one('span').removeClass(item.css_class);
          }
        });
    });
  widget.render();
};

// The default configuration used for wiring choice popup widgets.
var default_popup_choice_config = {
    container: Y,
    render_immediately: true,
    show_description: false,
    field_title: null
};

/**
 * Replace a legacy input widget with a popup choice widget.
 * @param legacy_node the YUI node containing the legacy widget.
 * @param field_name the Launchpad form field name.
 * @param choices the choices for the popup choice widget.
 * @param cfg configuration for the wiring action.
 * @param get_value_fn getter for the legacy widget's value.
 * @param set_value_fn setter for the legacy widget's value.
 */
var wirePopupChoice = function(legacy_node, field_name, choices, cfg,
                               get_value_fn, set_value_fn) {
    var choice_descriptions = {};
    Y.Array.forEach(choices, function(item) {
        choice_descriptions[item.value] = item.description;
    });
    var initial_field_value = get_value_fn(legacy_node);
    var choice_node = Y.Node.create([
        '<span class="' + field_name + '-content"><span class="value"></span>',
        '<a class="sprite edit editicon action-icon"',
        ' href="#">Edit</a></span>'
        ].join(''));
    if (cfg.show_description) {
        choice_node.append(Y.Node.create('<div class="formHelp"></div>'));
    }
    legacy_node.insertBefore(choice_node, legacy_node);
    if (cfg.show_description) {
        choice_node.one('.formHelp')
            .set('text', choice_descriptions[initial_field_value]);
    }
    legacy_node.addClass('hidden');
    if (!Y.Lang.isValue(cfg.field_title)) {
        cfg.field_title = field_name.replace('_', ' ');
    }
    var choice_edit = new Y.ChoiceSource({
        contentBox: choice_node,
        value: initial_field_value,
        title: 'Set ' + cfg.field_title + " as",
        items: choices,
        elementToFlash: choice_node,
        zIndex: 1050
    });
    if (cfg.render_immediately) {
        choice_edit.render();
    }

    var update_selected_value_css = function(selected_value) {
        Y.Array.each(choices, function(item) {
            if (item.value === selected_value) {
                choice_node.addClass(item.css_class);
            } else {
                choice_node.removeClass(item.css_class);
            }
        });
    };
    update_selected_value_css(initial_field_value);
    choice_edit.on('save', function(e) {
        var selected_value = choice_edit.get('value');
        update_selected_value_css(selected_value);
        set_value_fn(legacy_node, selected_value);
        if (cfg.show_description) {
            choice_node.one('.formHelp')
                .set('text', choice_descriptions[selected_value]);
        }
    });
    return choice_edit;
};

/**
 * Replace a drop down combo box with a popup choice selection widget.
 * @param field_name
 * @param choices
 * @param cfg
 */
namespace.addPopupChoice = function(field_name, choices, cfg) {
    cfg = Y.merge(default_popup_choice_config, cfg);
    var legacy_node = cfg.container.one('[id="field.' + field_name + '"]');
    if (!Y.Lang.isValue(legacy_node)) {
        return;
    }
    var get_fn = function(node) {
        return node.get('value');
    };
    var set_fn = function(node, value) {
        node.set('value', value);
    };
    return wirePopupChoice(
        legacy_node, field_name, choices, cfg, get_fn, set_fn);
};

/**
 * Replace a radio button group with a popup choice selection widget.
 * @param field_name
 * @param choices
 * @param cfg
 */
namespace.addPopupChoiceForRadioButtons = function(field_name, choices, cfg) {
    if (!choices || choices.length === 0) {
        throw 'No choices for the popup.';
    }
    cfg = Y.merge(default_popup_choice_config, cfg);
    var field_node = cfg.container.one('[name="field.' + field_name + '"]');
    if (!Y.Lang.isValue(field_node)) {
        return;
    }
    var legacy_node = field_node.ancestor('table.radio-button-widget');
    if (!Y.Lang.isValue(legacy_node)) {
        return;
    }
    var get_fn = function(node) {
        var field_value = choices[0].value;
        node.all('input[name="field.' + field_name + '"]').each(function(node) {
            if (node.get('checked')) {
                field_value = node.get('value');
            }
        });
        return field_value;
    };
    var set_fn = function(node, value) {
        node.all('input[name="field.' + field_name + '"]')
                .each(function(node) {
            var node_selected = node.get('value') === value;
            node.set('checked', node_selected);
            if (node_selected) {
                node.simulate('change');
            }
        });
    };
    return wirePopupChoice(
        legacy_node, field_name, choices, cfg, get_fn, set_fn);
};

/* XXX: AaronBentley 2012-09-18 bug=1052618 array-extras needed to enable
 * Y.Array.forEach in YUI 3.3, but not needed in 3.5
 */

}, "0.1", {
    requires: ["lp.ui.choiceedit", "lp.client.plugins", "node-event-simulate",
               "array-extras"]
});
