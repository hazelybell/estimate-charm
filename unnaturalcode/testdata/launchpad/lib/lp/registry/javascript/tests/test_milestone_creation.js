YUI.add('lp.registry.javascript.tests.test_milestone_creation', function (Y) {
/**
 * Integration tests for milestoneoverlay.
 */
var serverfixture = Y.lp.testing.serverfixture;
// Define the module-under-test.
var the_module = Y.lp.registry.milestoneoverlay;

var makeTestConfig = function(config) {
  if (Y.Lang.isUndefined(config)) {
    config = {};
  }
  config.on = Y.merge(
    {
      success: function(result) {
          config.successful = true;
          config.result = result;
      },
      failure: function(tid, response, args) {
          config.successful = false;
          config.result = {tid: tid, response: response, args: args};
      }
    },
    config.on);
  return config;
};

/**
 * Test milestoneoverlay interaction via the API, such as creating
 * milestones and adding tags.
 */
var tests = Y.namespace(
    'lp.registry.javascript.tests.test_milestone_creation');
tests.suite = new Y.Test.Suite(
    'lp.registry.javascript.milestoneoverlay facet Tests');
tests.suite.add(new Y.Test.Case({
    name: 'Milestone creation tests',

    tearDown: function() {
        // Always do this.
        serverfixture.teardown(this);
    },

    test_configure: function() {
        // Ensure configuring the module works as it will be needed in
        // subsequent tests.
        var client = new Y.lp.client.Launchpad({sync: true});
        var config = {
            milestone_form_uri: 'a',
            series_uri: 'b',
            next_step: function() {}
        };
        the_module.configure(config);
    },

    test_milestone_test_fixture_setup: function() {
        // Setup the fixture, retrieving the objects we need for the test.
        var data = serverfixture.setup(this, 'setup');
        var client = new Y.lp.client.Launchpad({sync: true});
        var product = new Y.lp.client.Entry(
            client, data.product, data.product.self_link);
        var product_name = product.get('name');
        Y.Assert.areEqual('my-test-project', product_name);
    },

    test_milestone_creation_no_tags: function() {
        // Setup the fixture, retrieving the objects we need for the test.
        var data = serverfixture.setup(this, 'setup');

        // Initialize the milestoneoverlay module.
        var milestone_table = Y.lp.registry.milestonetable;
        var client = new Y.lp.client.Launchpad({sync: true});
        var config = {
            milestone_form_uri: data.milestone_form_uri,
            series_uri: data.series_uri,
            lp_client: client
        };
        the_module.configure(config);
        the_module.setup_milestone_form();

        var milestone_name = 'new-milestone';
        var code_name = 'new-codename';
        var params = {
            'field.name': [milestone_name],
            'field.code_name': [code_name],
            'field.dateexpected': [''],
            'field.tags': [''],
            'field.summary': ['']
        };

        // Test the creation of the new milestone.
        the_module.last_error = null;
        the_module.save_new_milestone(params);
        Y.Assert.isNull(the_module.last_error,
            "last_error is: " + the_module.last_error);

        // Verify the milestone was created.
        var product = new Y.lp.client.Entry(
            client, data.product, data.product.self_link);
        config = makeTestConfig({parameters: {name: milestone_name}});
        // Get the new milestone.
        product.named_get('getMilestone', config);
        Y.Assert.isTrue(config.successful, 'Getting milestone failed');
        var milestone = config.result;
        Y.Assert.isInstanceOf(
            Y.lp.client.Entry, milestone, 'Milestone is not an Entry');
        Y.Assert.areEqual(milestone_name, milestone.get('name'));
        Y.Assert.areEqual(code_name, milestone.get('code_name'));
        // Ensure no tags are created.
        config = makeTestConfig({parameters: {}});
        milestone.named_get('getTags', config);
        Y.Assert.isTrue(config.successful, 'call to getTags failed');
        var expected = [];
        Y.ArrayAssert.itemsAreEqual(expected, config.result);
    },

    test_milestone_creation_with_tags: function() {
        // Setup the fixture, retrieving the objects we need for the test.
        var data = serverfixture.setup(this, 'setup');

        // Initialize the milestoneoverlay module.
        var milestone_table = Y.lp.registry.milestonetable;
        var client = new Y.lp.client.Launchpad({sync: true});
        var config = {
            milestone_form_uri: data.milestone_form_uri,
            series_uri: data.series_uri,
            lp_client: client
        };
        the_module.configure(config);
        the_module.setup_milestone_form();

        var milestone_name = 'new-milestone';
        var code_name = 'new-codename';
        var tags = ['zeta  alpha beta'];
        var params = {
            'field.name': [milestone_name],
            'field.code_name': [code_name],
            'field.dateexpected': [''],
            'field.tags': tags,
            'field.summary': ['']
        };

        // Test the creation of the new milestone.
        the_module.last_error = null;
        the_module.save_new_milestone(params);
        Y.Assert.isNull(the_module.last_error,
            "last_error is: " + the_module.last_error);

        // Verify the milestone was created.
        var product = new Y.lp.client.Entry(
            client, data.product, data.product.self_link);
        config = makeTestConfig({parameters: {name: milestone_name}});
        // Get the new milestone.
        product.named_get('getMilestone', config);
        Y.Assert.isTrue(config.successful, 'Getting milestone failed');
        var milestone = config.result;
        Y.Assert.isInstanceOf(
            Y.lp.client.Entry, milestone, 'Milestone is not an Entry');
        Y.Assert.areEqual(milestone_name, milestone.get('name'));
        Y.Assert.areEqual(code_name, milestone.get('code_name'));
        // Ensure the tags are created.
        config = makeTestConfig({parameters: {}});
        milestone.named_get('getTags', config);
        Y.Assert.isTrue(config.successful, 'call to getTags failed');
        var expected = ["alpha", "beta", "zeta"];
        Y.ArrayAssert.itemsAreEqual(expected, config.result);
    }
}));

}, '0.1', {
    requires: [
        'test', 'lp.client', 'lp.testing.serverfixture',
        'lp.registry.milestonetable', 'lp.registry.milestoneoverlay']
});

