YUI.add('lp.app.multicheckbox', function(Y) {

var namespace = Y.namespace('lp.app.multicheckbox');

/* Add a multicheckbox widget which will PATCH a given attribute on
 * a given resource.
 *
 * @method addMultiCheckboxPatcher
 * @param {Array} items The items which to display as checkboxes.
 * @param {String} help_text The text to display beneath the checkboxes.
 * @param {String} resource_uri The object being modified.
 * @param {String} attribute_name The attribute on the resource being
 *                                modified.
 * @param {String} attribute_type The attribute type.
 *     "reference": the items are object references
 *     Other values are currently ignored.
 * @param {String} content_box_id
 * @param {Object} config Object literal of config name/value pairs.
 *     config.header: a line of text at the top of the widget.
 *     config.step_title: overrides the subtitle.
 */
namespace.addMultiCheckboxPatcher = function (
    items, help_text, resource_uri, attribute_name, attribute_type,
    content_box_id, config, client) {

    // We may have been passed a mock client for testing but if not, create
    // a proper one.
    if (client === undefined) {
        client = new Y.lp.client.Launchpad();
        }

    var content_box = Y.one('#'+content_box_id);
    var result_node = Y.one('#'+content_box_id+'-items');
    var widget_node = Y.one('#'+attribute_name);
    var activator = new Y.lp.ui.activator.Activator(
        {contentBox: content_box, animationNode: widget_node});

    var failure_handler = function (id, response, args) {
        activator.renderFailure(
            Y.Node.create(
                '<div>' + response.statusText +
                    '<pre>' + response.responseText + '</pre>' +
                '</div>'));
    };

    // The function called to save the selected items.
    function save(result) {
        activator.renderProcessing();
        var success_handler = function (entry) {
            result_node.setContent(entry.getHTML(attribute_name));
            activator.renderSuccess(result_node);
        };

        var patch_payload = {};
        patch_payload[attribute_name] = result;
        client.patch(resource_uri, patch_payload, {
            accept: 'application/json;include=lp_html',
            on: {
                success: success_handler,
                failure: failure_handler
            }
        });
    }

    config.save = save;
    config.content_box_id = content_box_id;
    var editform = namespace.create(
            attribute_name, attribute_type, items, help_text, config);
    activator.subscribe('act', function (e) {
        editform.show();
    });
    activator.render();
    return editform;
};


/**
  * Creates a multicheckbox widget that has already been rendered and hidden.
  *
  * @requires dom, lp.ui.activator, lp.ui.overlay
  * @method create
  * @param {String} attribute_name The attribute on the resource being
  *                                modified.
  * @param {String} attribute_type The attribute type.
  *     "reference": the items are object references
  *     Other values are currently ignored.
  * @param {Array} items Items for which to create checkbox elements.
  * @param {String} help_text text display below the checkboxes.
  * @param {Object} config Optional Object literal of config name/value pairs.
  *                        config.header is a line of text at the top of
  *                        the widget.
  *                        config.save is a Function (optional) which takes
  *                        a single string argument.
  */
namespace.create = function (attribute_name, attribute_type, items, help_text,
                             config) {
    var header;
    if (config !== undefined) {
        header = 'Choose an item.';
        if (config.header !== undefined) {
            header = config.header;
        }
    }

    // The html for each checkbox.
    var CHECKBOX_TEMPLATE =
        ['<label style="{item_style}" for="{field_name}.{field_index}">',
        '<input id="{field_name}.{field_index}" ',
        'name="{field_name}.{field_index}" ',
        'class="checkboxType" type="checkbox" value="{field_value}" ',
        '{item_checked}>&nbsp;{field_text}</label>'].join("");

    var content = Y.Node.create("<div/>");
    var header_node = Y.Node.create(
        "<div class='yui3-lazr-formoverlay-form-header'/>");
    content.appendChild(header_node);
    var body = Y.Node.create("<div class='yui3-widget-bd'/>");

    // Set up the nodes for each checkbox.
    var choices_nodes = Y.Node.create('<ul id="'+attribute_name+'.items"/>');
    // A mapping from checkbox value attributes (data token) -> data values
    var item_value_mapping = {};
    Y.Array.each(items, function(data, i) {
        var checked_html = '';
        if (data.checked) {
            checked_html = 'checked="checked"';
            }
        var checkbox_html = Y.Lang.sub(
            CHECKBOX_TEMPLATE,
            {field_name: "field."+attribute_name, field_index:i,
            field_value: data.token, field_text: Y.Escape.html(data.name),
            item_style: data.style, item_checked: checked_html});

        var choice_item = Y.Node.create("<li/>");
        choice_item.setContent(checkbox_html);
        choices_nodes.appendChild(choice_item);
        item_value_mapping[data.token] = data.value;
    }, this);
    body.appendChild(choices_nodes);
    content.appendChild(body);
    var help_node = Y.Node.create("<p class='formHelp'>"+help_text+"</p>");
    content.appendChild(help_node);

    var save_button = Y.Node.create(
        '<button id="'+config.content_box_id+'-save">Save</button>');
    var save_callback = function(data) {
        editform.hide();
        var result = namespace.getSelectedItems(
            data, item_value_mapping, attribute_type);
        config.save(result);
    };
    var new_config = Y.merge(config, {
        align: {
            points: [Y.WidgetPositionAlign.CC,
                     Y.WidgetPositionAlign.CC]
        },
        progressbar: true,
        progress: 100,
        headerContent: "<h2>" + header + "</h2>",
        centered: true,
        zIndex: 1000,
        visible: false,
        form_content: content,
        form_submit_button: save_button,
        form_cancel_button: Y.Node.create(
            '<button type="button">Cancel</button>'),
        form_submit_callback: save_callback
        });
    var editform = new Y.lp.ui.FormOverlay(new_config);
    editform.render();
    return editform;
};


/*
 * Return a list of the selected checkbox values.
 * Exposed via the namespace so it is accessible to tests.
 */
namespace.getSelectedItems = function(data, item_value_mapping,
                                      attribute_type) {
    var result = [];
    Y.each(data, function(item_token, key) {
            var item_value = item_value_mapping[item_token];
            var marshalled_value = marshall(item_value, attribute_type);
            result.push(marshalled_value);
    });
    return result;
};


/*
 * Transform the selected value according to the attribute type we are editing
 */
function marshall(value, attribute_type) {
    switch (attribute_type) {
        case "reference":
            var item_value = Y.lp.client.normalize_uri(value);
            return Y.lp.client.get_absolute_uri(item_value);
        default:
            return value;
    }
}

}, "0.1", {"requires": [
    "dom", "escape", "lp.ui.formoverlay", "lp.ui.activator", "lp.client"
    ]});
