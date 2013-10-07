/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Form Widgets.
 *
 * @module lp.app
 * @submodule formwidgets
 */

YUI.add('lp.app.formwidgets', function(Y) {

Y.log('loading lp.app.formwidgets');

var namespace = Y.namespace('lp.app.formwidgets');

var owns = Y.Object.owns,
    values = Y.Object.values,
    attrcaller = Y.lp.extras.attrcaller;


/**
 * A form row matching that which LaunchpadForm presents, containing a
 * field (defined in a subclass), and an optional label and
 * description.
 *
 * @class FormRowWidget
 */
var FormRowWidget;

FormRowWidget = function() {
    FormRowWidget.superclass.constructor.apply(this, arguments);
};

Y.mix(FormRowWidget, {

    NAME: 'formRowWidget',

    ATTRS: {

        /**
         * The field name.
         *
         * @property name
         */
        name: {
            setter: function(value, name) {
                this.fieldNode.all("input, select").set("name", value);
            }
        },

        /**
         * The top label for the field.
         *
         * @property label
         */
        label: {
            getter: function() {
                return this.labelNode.get("text");
            },
            setter: function(value, name) {
                this.labelNode.set("text", value);
            }
        },

        /**
         * A dictionary {link:link, text:text} to populate
         * the pop-up help for the field.
         *
         * @property help
         */
        help: {
            getter: function() {
                return {link:this.helpNode.one('a')
                            .get("href"),
                        text:this.helpNode
                            .get("text")};
            },
            setter: function(value, name) {
                if ((value.link !== undefined) &&
                    (value.text !== undefined)) {
                    this.helpNode.one('a').set("href", value.link)
                        .set("text", value.text);
                    this.helpNode.removeClass('hidden');
                }
                else {
                    this.helpNode.addClass('hidden');
                }
            }
        },

        /**
         * A description shown near the field.
         *
         * @label description
         */
        description: {
            getter: function() {
                return this.descriptionNode.get("text");
            },
            setter: function(value, name) {
                this.descriptionNode.set("text", value);
            }
        }
    }

});

Y.extend(FormRowWidget, Y.Widget, {

    BOUNDING_TEMPLATE: "<tr></tr>",

    CONTENT_TEMPLATE: '<td colspan="2"></td>',

    initializer: function(config) {
        this.labelNode = Y.Node.create("<label />");
        this.helpNode = Y.Node.create(('<span class="helper hidden">'+
            '<a href=""' +
            'target="help" class="sprite maybe action-icon"></a></span>'));
        this.fieldNode = Y.Node.create("<div></div>");
        this.descriptionNode = Y.Node.create('<p class="formHelp" />');
        this.spinnerNode = Y.Node.create(
            '<img src="/@@/spinner" alt="Loading..." />');
    },

    renderUI: function() {
        this.get("contentBox")
            .append(this.labelNode)
            .append(this.helpNode)
            .append(this.fieldNode)
            .append(this.descriptionNode);
    },

    /**
     * Show the spinner.
     *
     * @method showSpinner
     */
    showSpinner: function() {
        this.fieldNode.empty().append(this.spinnerNode);
    },

    /**
     * Hide the spinner.
     *
     * @method hideSpinner
     */
    hideSpinner: function() {
        this.spinnerNode.remove();
    },

    /**
     * Display an error.
     *
     * @method showError
     */
    showError: function(error) {
        this.fieldNode
            .append(Y.Node.create('<div />')
                .addClass('message')
                .set("text", error))
            .ancestor('tr')
                .addClass('error');
        Y.lp.anim.red_flash({node: this.fieldNode.one('.message')}).run();
    },

    /**
     * Hide any previously displayed error.
     *
     * @method hideError
     */
    hideError: function(error) {
        this.fieldNode.all('.message').remove();
        this.fieldNode.ancestor('tr').removeClass('error');
    },

    /**
     * Validate this widget. Subclasses can override this method.
     * It should return true if the widget validates and false otherwise.
     * It is also responsible for setting any error on the widget using
     * this.showError.
     *
     * @method validate
     */
    validate: function() {
        return true;
    }

});

namespace.FormRowWidget = FormRowWidget;


/**
 * A form row matching that which LaunchpadForm presents, containing a
 * list of checkboxes, and an optional label and description.
 *
 * @class ChoiceListWidget
 */
var ChoiceListWidget;

ChoiceListWidget = function() {
    ChoiceListWidget.superclass.constructor.apply(this, arguments);
};

Y.mix(ChoiceListWidget, {

    NAME: 'choiceListWidget',

    ATTRS: {

        /**
         * An array of strings from which to choose.
         *
         * @property choices
         */
        choices: {
            getter: function() {
                return this.fieldNode.all("li").map(
                    this._choiceFromNode, this);
            },
            setter: function(value, name) {
                var compare = Y.bind(this._compareChoices, this);
                var choices = this._convertChoices(value).sort(compare);
                var create = Y.bind(this._nodeFromChoice, this);
                var list = Y.Node.create("<ul />");
                var append = Y.bind(list.append, list);
                choices.map(create).forEach(append);
                var selection = this.get("choice");
                this.fieldNode.empty().append(list);
                this.set("choice", selection);
            }
        },

        /**
         * The current selection.
         *
         * @property choice
         */
        choice: {
            setter: function(value, name) {
                if (value === null) {
                    // De-select everything.
                    this.fieldNode.all("li > input").set("checked", false);
                }
                else {
                    var choices = this._convertChoices(
                        Y.Lang.isArray(value) ? value : [value]);
                    var choicemap = {};
                    choices.forEach(
                        function(choice) {
                            choicemap[choice.value] = true;
                        }
                    );
                    this.fieldNode.all("li > input").each(
                        function(node) {
                            var checked = owns(choicemap, node.get("value"));
                            node.set("checked", checked);
                        }
                    );
                }
            },
            getter: function() {
                var inputs = this.fieldNode.all("li > input:checked");
                var nodes = inputs.map(attrcaller("ancestor"));
                var choice = nodes.map(this._choiceFromNode, this);
                if (!this.get("multiple")) {
                    if (choice.length === 0) {
                        choice = null;
                    }
                    else if (choice.length === 1) {
                        choice = choice[0];
                    }
                    else {
                        choice = undefined;
                    }
                }
                return choice;
            }
        },

        /**
         * Whether multiple choices can be made.
         *
         * @property multiple
         */
        multiple: {
            value: true,
            setter: function(value, name) {
                value = value ? true : false;
                var field_type = value ? "checkbox" : "radio";
                this.fieldNode.all("li > input").set("type", field_type);
                return value;
            }
        }

    }

});

Y.extend(ChoiceListWidget, FormRowWidget, {

    /**
     * Convert a "bare" choice into a object choice with text and
     * value keys.
     *
     * @param {String|Object} choice
     */
    _convertChoice: function(choice) {
        return Y.Lang.isString(choice) ?
            {value: choice, text: choice} : choice;
    },

    /**
     * Convert an array of choices using _convertChoice.
     *
     * @param {Array|Y.Array} choices
     */
    _convertChoices: function(choices) {
        return Y.Array.map(choices, this._convertChoice, this);
    },

    /**
     * Default method to sort choices.
     *
     * @param {Object|String} ca A choice. If it is an object it must
     *     contain a <code>text</code> attribute.
     * @param {Object|String} cb A choice. If it is an object it must
     *     contain a <code>text</code> attribute.
     */
    _compareChoices: function(ca, cb) {
        var keya = Y.Lang.isObject(ca) ? ca.text : ca,
            keyb = Y.Lang.isObject(cb) ? cb.text : cb;
        if (keya === keyb) {
            return 0;
        }
        else {
            return (keya > keyb) ? 1 : -1;
        }
    },

    /**
     * Return a node that represents the given choice object.
     *
     * @method _nodeFromChoice
     */
    _nodeFromChoice: function(choice) {
        var field_name = this.get("name");
        var field_type = this.get("multiple") ? "checkbox" : "radio";
        var item = Y.Node.create(
            "<li><input /> <label /></li>");
        item.one("input")
            .set("type", field_type)
            .set("name", field_name)
            .set("value", choice.value);
        item.one("label")
            .setAttribute(
                "for", item.one("input").generateID())
            .setStyle("font-weight", "normal")
            .set("text", choice.text);
        item.setData(choice.data)
            .setStyle("overflow", "hidden")
            .setStyle("text-overflow", "ellipsis")
            .setStyle("white-space", "nowrap");
        return item;
    },

    /**
     * Return a choice object represented by the given node.
     *
     * @method _choiceFromNode
     */
    _choiceFromNode: function(node) {
        return {
            data: node.getData(),
            text: node.one("label").get("text"),
            value: node.one("input").get("value")
        };
    },

    /**
     * Utility method to validate that the list of selected choices is a
     * subset of the given list.
     *
     * @method validate_choice_among
     */
    validate_choice_among: function(superset) {
        var choices = this.get(
            "multiple") ? this.get('choice') : [this.get('choice')];
        return !Y.Array.some(choices, function(choice) {
            return (Y.Array.indexOf(superset, choice.value) === -1);
        });
     },

    /**
     * Remove a list of choices from the possible widget's choices.
     *
     * @method remove_choices
     */
    remove_choices: function(choices) {
        var choicemap = {};
        // Create a mapping of value -> choice for the given choices.
        this._convertChoices(choices).forEach(
            function(choice) {
                choicemap[choice.value] = true;
            }
        );
        // Filter out the choices mentioned.
        var newchoices = this.get("choices").filter(function(choice) {
            return !owns(choicemap, choice.value);
        });
        // Set back again.
        this.set("choices", newchoices);
        // Tell everyone!
        this.fire("removed_choices", this, choices);
        Y.lp.anim.green_flash({node: this.fieldNode}).run();
    },

    /**
     * Add new choices (if they are not already present).
     *
     * @method add_choices
     */
    add_choices: function(choices) {
        var choicemap = {};
        // Create a mapping of value -> choice for the given choices.
        this._convertChoices(choices).forEach(
            function(choice) {
                choicemap[choice.value] = choice;
            }
        );
        // Allow existing choices to be redefined.
        var newchoices = this.get("choices").map(function(choice) {
            if (owns(choicemap, choice.value)) {
                choice = choicemap[choice.value];
                delete choicemap[choice.value];
            }
            return choice;
        });
        // Add the new choices (i.e. what remains in choicemap).
        newchoices = newchoices.concat(values(choicemap));
        // Set back again.
        this.set("choices", newchoices);
        // Tell everyone!
        this.fire("added_choices", this, choices);
        Y.lp.anim.green_flash({node: this.fieldNode}).run();
    }

});


namespace.ChoiceListWidget = ChoiceListWidget;


/**
 * A widget to encapsulate functionality around the form actions.
 *
 * @class FormActionsWidget
 */
var FormActionsWidget;

FormActionsWidget = function() {
    FormActionsWidget
        .superclass.constructor.apply(this, arguments);
};

FormActionsWidget.ATTRS = {
    duration: {
        value: 1.0
    },

    height: {
        value: 0
    },

    opacity: {
        value: 0
    }
};


Y.mix(FormActionsWidget, {

    NAME: 'formActionsWidget',

    HTML_PARSER: {
        submitButtonNode: "input[type=submit]"
    }

});

Y.extend(FormActionsWidget, Y.Widget, {

    initializer: function(config) {
        this.client = new Y.lp.client.Launchpad();
        this.error_handler = new Y.lp.client.ErrorHandler();
        this.error_handler.clearProgressUI = Y.bind(this.hideSpinner, this);
        this.error_handler.showError = Y.bind(this.showError, this);
        this.submitButtonNode = config.submitButtonNode;
        this._widgets = [];
        this.spinnerNode = Y.Node.create(
            '<img src="/@@/spinner" alt="Loading..." />');
    },

    /**
     * Register a widget as part of this encapsulating widget.
     * Only register the widget if it is not null.
     *
     * @method registerWidget
     */
    registerWidget: function(widget) {
        if (widget !== null) {
            this._widgets.push(widget);
        }
    },

    /**
     * Validate the coherence of the contained widgets.
     * Subclasses can override this method. It is meant to be used when
     * there is validation involving more than one widget that needs to
     * happen.
     *
     * @method validate_all
     */
    validate_all: function() {
        return true;
    },

    /**
     * Validate all the registered widgets. Display a global error
     * displaying the number of errors if any of the encapsulated widgets
     * fails to validate.
     *
     * @method validate
     */
    validate: function() {
        var i;
        var error_number = 0;
        for (i = 0; i < this._widgets.length; i++) {
            if (this._widgets[i].validate() === false) {
                error_number = error_number + 1;
            }
        }
        if (error_number !== 0) {
            this.showNErrors(error_number);
            return false;
        }
        return this.validate_all();
    },

    showNErrors: function(error_number) {
        this.hideError();
        if (error_number !== 0) {
            if (error_number === 1) {
                this.showError('There is 1 error.');
            }
            else {
                this.showError('There are ' + error_number + ' errors.');
            }
        }
    },

    /**
     * Show the spinner, and hide the submit button.
     *
     * @method showSpinner
     */
    showSpinner: function() {
        this.submitButtonNode.replace(this.spinnerNode);
    },

    /**
     * Hide the spinner, and show the submit button again.
     *
     * @method hideSpinner
     */
    hideSpinner: function() {
        this.spinnerNode.replace(this.submitButtonNode);
    },

    /**
     * Display an error.
     *
     * @method showError
     */
    showError: function(error) {
        this.hideError();
        Y.Node.create('<p class="error message" />')
            .appendTo(this.get("contentBox"))
            .set("text", error);
    },

    /**
     * Remove the error that has been previously displayed by showError.
     *
     * @method hideError
     */
    hideError: function() {
        this.get("contentBox").all("p.error.message").remove();
    },

    /**
     * Remove all the errors (including these displayed on the contained
     * widgets).
     *
     * @method hideErrors
     */
    hideErrors: function(error) {
        this.hideError();
        var i;
        for (i = 0; i < this._widgets.length; i++) {
            this._widgets[i].hideError();
        }
    }

});

namespace.FormActionsWidget = FormActionsWidget;


}, "0.1", {"requires": ["node", "dom", "io", "widget", "lp.client",
                        "lp.extras", "lp.anim", "array-extras",
                        "transition"]});
