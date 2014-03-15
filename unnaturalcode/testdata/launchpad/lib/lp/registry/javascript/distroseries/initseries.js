/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * DistroSeries Initialization.
 *
 * @module lp.registry.distroseries
 * @submodule initseries
 */

YUI.add('lp.registry.distroseries.initseries', function(Y) {

Y.log('loading lp.registry.distroseries.initseries');

var namespace = Y.namespace('lp.registry.distroseries.initseries');

var widgets = Y.lp.registry.distroseries.widgets,
    formwidgets = Y.lp.app.formwidgets,
    attrselect = Y.lp.extras.attrselect;


/**
 * A widget to encapsulate functionality around the form actions.
 *
 * @class DeriveDistroSeriesActionsWidget
 */
var DeriveDistroSeriesActionsWidget;

DeriveDistroSeriesActionsWidget = function() {
    DeriveDistroSeriesActionsWidget
        .superclass.constructor.apply(this, arguments);
};

Y.mix(DeriveDistroSeriesActionsWidget, {

    NAME: 'deriveDistroSeriesActionsWidget'

});

Y.extend(DeriveDistroSeriesActionsWidget, formwidgets.FormActionsWidget, {

    initializer: function(config) {
        this.context = config.context;
        this.deriveFromChoices = config.deriveFromChoices;
        this.registerWidget(this.deriveFromChoices);
        this.architectureChoice = config.architectureChoice;
        this.registerWidget(this.architectureChoice);
        this.architectureIndepChoice = config.architectureIndepChoice;
        this.registerWidget(this.architectureIndepChoice);
        this.packagesetChoice = config.packagesetChoice;
        this.registerWidget(this.packagesetChoice);
        this.packageCopyOptions = config.packageCopyOptions;
        this.registerWidget(this.packageCopyOptions);
        this.form_container = config.form_container;
    },

    /**
     * Display a success message then fade out and remove the form.
     *
     * @method success
     */
    success: function() {
        var message = [
            "The initialization of ", this.context.displayname,
            " has been scheduled and should run shortly."
        ].join("");
        var messageNode = Y.Node.create("<p />")
            .addClass("informational")
            .addClass("message")
            .set("text", message);
        var form = this.get("contentBox").ancestor("form");
        form.transition({
            duration: this.get('duration'), height: this.get('height'),
            opacity: this.get('opacity')}, function() { form.remove(true); });
        form.insert(messageNode, "after");
    },

    /**
     * Validate the coherence of the fields. Returns true if the form is
     * fit for submission. Returns false otherwise and displays appropriate
     * errors.
     *
     * @method validate
     */
    validate: function() {
        this.hideErrors();
        var arch_indep_choice = this.architectureIndepChoice.get(
            'choice').value;
        if (arch_indep_choice === this.architectureIndepChoice.AUTOSELECT) {
            // If no arch indep arch tag has been explicitely selected
            // check that one from the parents' is present among the selected
            // architectures.
            if (!this.architectureChoice.validate_arch_indep()) {
                this.architectureChoice.show_error_arch_indep();
                this.architectureIndepChoice.showError(
                    'Alternatively, you can specify the architecture ' +
                    'independent builder.');
                return false;
            }
        }
        else {
            // Check that the arch indep arch tag is among the selected
            // architectures.
            var choices_objs = this.architectureChoice.get('choice');
            if (choices_objs.length !== 0) {
                var choices = Y.Array.map(
                    choices_objs,
                    function(choice_obj) { return choice_obj.value; });
                if (!this.architectureIndepChoice.validate_choice_among(
                         choices)) {
                    this.architectureIndepChoice.showError(
                        'The selected architecture independent builder is ' +
                        'not among the selected architectures.');
                    return false;
                }
            }
        }
        return true;
    },

    /**
     * Validate all the widgets and call submit as appropriate.
     *
     * @method submit
     */
    check_and_submit: function() {
        if (this.validate()) {
            this.submit();
        }
    },

    /**
     * Call deriveDistroSeries via the API.
     *
     * @method submit
     */
    submit: function() {
        var self = this;
        var values = attrselect("value");
        var arch_indep = values(
            this.architectureIndepChoice.get("choice"))[0];
        var config = {
            on: {
                start: function() {
                    self.hideErrors();
                    self.showSpinner();
                },
                success: function() {
                    self.hideSpinner();
                    self.success();
                },
                failure: this.error_handler.getFailureHandler()
            },
            parameters: {
                name: this.context.name,
                distribution: this.context.distribution_link,
                parents: this.deriveFromChoices.get("parents"),
                architectures:
                    values(this.architectureChoice.get("choice")),
                archindep_archtag:
                    arch_indep === this.architectureIndepChoice.AUTOSELECT ?
                        null : arch_indep,
                packagesets: this.packagesetChoice !== null ?
                    values(this.packagesetChoice.get("choice")) : [],
                rebuild:
                    this.packageCopyOptions.get("choice").value === "rebuild",
                overlays: this.deriveFromChoices.get("overlays"),
                overlay_pockets: this.deriveFromChoices.get(
                    "overlay_pockets"),
                overlay_components: this.deriveFromChoices.get(
                    "overlay_components")
            }
        };
        this.client.named_post(
            this.context.self_link, "initDerivedDistroSeries", config);
    }

});

namespace.DeriveDistroSeriesActionsWidget = DeriveDistroSeriesActionsWidget;

/*
 * Show the "Add parent series" overlay.
 */
var show_add_parent_series_form = function(e) {

    e.preventDefault();
    var config = {
        header: 'Add a parent series',
        step_title: 'Search'
    };

    config.save = function(result) {
        add_parent_series(result);
    };

    var parent_picker =
        Y.lp.app.picker.create('DistroSeriesDerivation', config);
    parent_picker.show();
};

namespace.show_add_parent_series_form = show_add_parent_series_form;

/*
 * Add a parent series.
 */
var add_parent_series = function(parent) {
    Y.fire("add_parent", parent);
};

namespace.add_parent_series = add_parent_series;


/**
 * Setup the widgets on the +initseries page.
 *
 * @function setup
 */
namespace.setup = function(cache) {
    var form_actions = namespace.setupWidgets(cache);
    namespace.setupInteraction(form_actions, cache);
};

/**
 * Setup the widgets objects and return the form object.
 *
 * @function setupWidgets
 * @param {Object} cache Specify the value cache to use. If not
 *     specified, LP.cache is used. Intended chiefly for testing.
 */
namespace.setupWidgets = function(cache) {
    if (cache === undefined) { cache = LP.cache; }

    var form_container = Y.one("#initseries-form-container");
    var form_table = form_container.one("table.form");
    var form_table_body = form_table.append(Y.Node.create('<tbody />'));

    // Widgets.
    var add_parent_link = Y.Node.create('<a href="+add-parent-series">')
            .addClass("sprite")
            .addClass("add")
            .set("id", "add-parent-series")
            .set("text", "Add parent series");
    add_parent_link.appendTo(form_table_body);
    var parents_selection =
        new widgets.ParentSeriesListWidget()
            .set("name", "field.parent")
            .set("label", "Parent Series:")
            .set("description",
                     "Choose and configure the parent series.")
            .render(form_table_body);
    var architecture_choice =
        new widgets.ArchitecturesChoiceListWidget()
            .set("name", "field.architectures")
            .set("label", "Architectures:")
            .set("description",
                     "Choose the architectures you want to " +
                     "use from the parent series (or select none " +
                     "if you want to use all the available " +
                     "architectures).")
            .render(form_table_body);
    var arch_indep_choice =
       new widgets.ArchIndepChoiceListWidget()
            .set("name", "field.archindep_archtag")
            .set("label", "Architecture independent builder:")
            .set("description",
                     "Choose the architecture tag that should be " +
                     "used to build architecture independent binaries.")
            .render(form_table_body);
    var packageset_choice = null;
    if (cache.is_first_derivation) {
        packageset_choice =
            new widgets.PackagesetPickerWidget()
                .set("name", "field.packagesets")
                .set("size", 5)
                .set("help", {link: '/+help-registry/init-series-packageset-help.html',
                              text: 'Packagesets help'})
                .set("multiple", true)
                .set("label", "Package sets to copy from parent:")
                .set("description",
                         "The package sets that will be imported " +
                         "into the derived distroseries (select none " +
                         "if you want to import all the available " +
                         "package sets).")
                .render(form_table_body);
    }
    var package_copy_options =
        new formwidgets.ChoiceListWidget()
            .set("name", "field.package_copy_options")
            .set("multiple", false)
            .set("label", "Copy options:")
            .set("description", (
                     "Choose whether to rebuild all the sources you copy " +
                     "from the parent(s), or to copy their binaries too."))
            .set("choices", [
                {text: "Copy Source and Rebuild", value: "rebuild"},
                {text: "Copy Source and Binaries", value: "copy"}])
            .set("choice", "copy")
            .render(form_table_body);
    var form_actions =
        new DeriveDistroSeriesActionsWidget({
            context: cache.context,
            srcNode: form_container.one("div.actions"),
            deriveFromChoices: parents_selection,
            architectureChoice: architecture_choice,
            architectureIndepChoice: arch_indep_choice,
            packagesetChoice: packageset_choice,
            packageCopyOptions: package_copy_options,
            form_container: form_container
        });

    return form_actions;
};

/**
 * Setup the interaction between the widgets.
 *
 * @function setupInteraction
 * @param {DeriveDistroSeriesActionsWidget} The form widget containing
 *     all the other widgets.
 * @param {Object} cache Specify the value cache to use. If not
 *     specified, LP.cache is used. Intended chiefly for testing.
 */
namespace.setupInteraction = function(form_actions, cache) {
    if (cache === undefined) { cache = LP.cache; }

    // Wire up the add parent series link.
    var link = Y.one('#add-parent-series');
    if (Y.Lang.isValue(link)) {
        link.addClass('js-action');
        link.on('click', show_add_parent_series_form);
    }

    Y.on('add_parent', function(parent) {
        var added = form_actions.deriveFromChoices.add_parent(parent);
        if (added) {
            Y.fire("parent_added", parent);
        }
    });

    form_actions.architectureChoice.on(
        form_actions.architectureChoice.name + ":added_choices",
        function(e, arch_list) {
            this.add_choices(arch_list);
        },
        form_actions.architectureIndepChoice);

    form_actions.architectureChoice.on(
        form_actions.architectureChoice.name + ":removed_choices",
        function(e, arch_list) {
            this.remove_choices(arch_list);
        },
        form_actions.architectureIndepChoice);

    if (cache.is_first_derivation) {
        // Wire the architecture and packageset pickers to the parent picker.
        Y.on('parent_added', function(parent) {
            form_actions.architectureChoice.add_distroseries(parent);
            form_actions.packagesetChoice.add_distroseries(parent);
        });

        Y.on('parent_removed', function(parent_id) {
            form_actions.architectureChoice.remove_distroseries(parent_id);
            form_actions.packagesetChoice.remove_distroseries(parent_id);
        });
    }
    else {
        // Disable rebuilding if cache.is_first_derivation is false.
        form_actions.packageCopyOptions.fieldNode
            .one('input[value="rebuild"]')
            .set('disabled', 'disabled');
        form_actions.packageCopyOptions.set("description",
            "Note that you cannot rebuild sources because the " +
            "distribution already has an initialized series.");
        // The architectures are those from the previous_series.
        form_actions.architectureChoice.set("description",
            "Choose the architectures you want to " +
            "use from the previous series (or select none " +
            "if you want to use all the available " +
            "architectures).");
        form_actions.architectureChoice.add_distroseries(
            cache.previous_series);
        // Setup the pre-selected parents (parents from the previous series).
        Y.each(
            cache.previous_parents,
            form_actions.deriveFromChoices.add_parent,
            form_actions.deriveFromChoices);
    }

    // Wire up the form check and submission.
    form_actions.form_container.one("form").on(
        "submit", function(event) {
            event.halt(); form_actions.check_and_submit(); });

    // Show the form.
    form_actions.form_container.removeClass("hidden");

};


}, "0.1", {"requires": [
               "node", "dom", "io", "widget", "array-extras",
               "transition", "lp.registry.distroseries.widgets",
               "lp.app.formwidgets", "lp.app.picker", "lp.extras"]});
