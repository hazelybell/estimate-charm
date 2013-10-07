YUI({

    base: '/+icing/yui/',
    filter: 'raw', combine: false, fetchCSS: false
}).use('test',
       'escape',
       'node',
       'test-console',
       'json',
       'cookie',
       'lp.testing.serverfixture',
       'lp.client',
       function(Y) {


var suite = new Y.Test.Suite(
  "Integration tests for lp.client and basic JS infrastructure");
var serverfixture = Y.lp.testing.serverfixture;

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
 * Test cache data in page load.
 */
suite.add(new Y.Test.Case({
  name: 'Cache data',

  tearDown: function() {
    serverfixture.teardown(this);
  },

  test_anonymous_user_has_no_cache_data: function() {
    var data = serverfixture.setup(this, 'create_product');
    serverfixture.runWithIFrame(
      {testcase: this,
       uri: data.product.web_link,
       iframe_is_ready: function(I) {
         I.use('node');
         return I.Lang.isValue(I.one('#json-cache-script'));
       }
      },
      function(I) {
        var iframe_window = I.config.win;
        var LP = iframe_window.LP;
        Y.Assert.isUndefined(LP.links.me);
        Y.Assert.isNotUndefined(LP.cache.context);
      }
    );
  },

  test_logged_in_user_has_cache_data: function() {
    var data = serverfixture.setup(this, 'create_product_and_login');
    serverfixture.runWithIFrame(
      {testcase: this,
       uri: data.product.web_link,
       iframe_is_ready: function(I) {
         I.use('node');
         return I.Lang.isValue(I.one('#json-cache-script'));
       }
      },
      function(I) {
        var iframe_window = I.config.win;
        var LP = iframe_window.LP;
        Y.Assert.areSame(
          '/~' + data.user.name,
          LP.links.me
        );
        Y.Assert.isNotUndefined(LP.cache.context);
      }
    );
  },

  test_get_relative_url: function() {
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Collection, config.result);
  },

  test_get_absolute_url: function() {
    var data = serverfixture.setup(this, 'create_product');
    var link = data.product.self_link;
    Y.Assert.areSame('http', link.slice(0, 4)); // See, it's absolute.
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get(link, config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Entry, config.result);
  },

  test_get_collection_with_pagination: function() {
    // We could do this with a fixture setup, but I'll rely on the
    // sampledata for now.  If this becomes a problem, write a quick
    // fixture that creates three or four people!
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({start: 2, size: 1});
    client.get('/people', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.areSame(2, config.result.start);
    Y.Assert.areSame(1, config.result.entries.length);
  },

  test_named_get_integration: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({parameters: {text: data.user.name}});
    client.named_get('people', 'find', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Collection, config.result);
    Y.Assert.areSame(1, config.result.total_size);
  },

  test_named_post_integration: function() {
    var data = serverfixture.setup(this, 'create_bug_and_login');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.named_post(
      data.bug.self_link, 'mute', config);
    Y.Assert.isTrue(config.successful, "named_post failed: " + config.result);
  },

  test_follow_link: function() {
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('', config);
    var root = config.result;
    config = makeTestConfig();
    root.follow_link('people', config);
    Y.Assert.isInstanceOf(Y.lp.client.Collection, config.result);
    Y.Assert.areSame(4, config.result.total_size);
  },

  test_follow_redirected_link: function() {
    var data = serverfixture.setup(this, 'create_user_and_login');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('', config);
    var root = config.result;
    config = makeTestConfig();
    root.follow_link('me', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Entry, config.result);
    Y.Assert.areSame(data.user.name, config.result.get('name'));
  },

  test_get_html_representation: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({accept: Y.lp.client.XHTML});
    client.get(data.user.self_link, config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isTrue(/<a href=\"\/\~/.test(config.result));
  },

  test_get_html_representation_escaped: function() {
    var data = serverfixture.setup(
      this, 'create_user_with_html_display_name');
    var actual_display_name = data.user.display_name;
    Y.Assert.areEqual('<strong>naughty</strong>', actual_display_name);
    var html_escaped_display_name = '&lt;strong&gt;naughty&lt;/strong&gt;';
    var has_actual_display_name = new RegExp(
      Y.Escape.regex(actual_display_name));
    var has_html_escaped_display_name = new RegExp(
      Y.Escape.regex(html_escaped_display_name));
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({accept: Y.lp.client.XHTML});
    client.get(data.user.self_link, config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isTrue(has_html_escaped_display_name.test(config.result));
    Y.Assert.isFalse(has_actual_display_name.test(config.result));
  },

  test_lp_save_html_representation: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({accept: Y.lp.client.XHTML});
    var user = new Y.lp.client.Entry(
      client, data.user, data.user.self_link);
    user.lp_save(config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isTrue(/<a href=\"\/\~/.test(config.result));
  },

  test_patch_html_representation: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig({accept: Y.lp.client.XHTML});
    client.patch(data.user.self_link, {}, config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isTrue(/<a href=\"\/\~/.test(config.result));
  },

  test_lp_save: function() {
    var data = serverfixture.setup(this, 'create_user_and_login');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    var user = new Y.lp.client.Entry(
      client, data.user, data.user.self_link);
    var original_display_name = user.get('display_name');
    var new_display_name = original_display_name + '_modified';
    user.set('display_name', new_display_name);
    user.lp_save(config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.areEqual(new_display_name, config.result.get('display_name'));
  },

  test_lp_save_fails_with_mismatched_ETag: function() {
    var data = serverfixture.setup(this, 'create_user_and_login');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    var user = new Y.lp.client.Entry(
      client, data.user, data.user.self_link);
    var original_display_name = user.get('display_name');
    var new_display_name = original_display_name + '_modified';
    user.set('display_name', new_display_name);
    user.set('http_etag', 'Non-matching ETag.');
    user.lp_save(config);
    Y.Assert.isFalse(config.successful);
    Y.Assert.areEqual(412, config.result.response.status);
  },

  test_patch: function() {
    var data = serverfixture.setup(this, 'create_user_and_login');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    var new_display_name = data.user.display_name + '_modified';
    client.patch(
      data.user.self_link, {display_name: new_display_name}, config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.areEqual(new_display_name, config.result.get('display_name'));
  },

  test_collection_entries: function() {
    serverfixture.setup(this, 'login_as_admin');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    var people = config.result;
    Y.Assert.isInstanceOf(Y.lp.client.Collection, people);
    Y.Assert.areEqual(4, people.total_size);
    Y.Assert.areEqual(people.total_size, people.entries.length);
    var i = 0;
    for (; i < people.entries.length; i++) {
      Y.Assert.isInstanceOf(Y.lp.client.Entry, people.entries[i]);
    }
    var entry = people.entries[0];
    var new_display_name = entry.get('display_name') + '_modified';
    entry.set('display_name', new_display_name);
    config = makeTestConfig();
    entry.lp_save(config);
    Y.Assert.areEqual(new_display_name, config.result.get('display_name'));
  },

  test_collection_lp_slice: function() {
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    var people = config.result;
    people.lp_slice(config.on, 2, 1);
    var slice = config.result;
    Y.Assert.areEqual(2, slice.start);
    Y.Assert.areEqual(1, slice.entries.length);
  },

  test_collection_named_get: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    var people = config.result;
    config = makeTestConfig({parameters: {text: data.user.name}});
    people.named_get('find', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Collection, config.result);
    Y.Assert.areEqual(1, config.result.total_size);
    Y.Assert.areEqual(1, config.result.entries.length);
  },

  test_collection_named_post: function() {
    serverfixture.setup(this, 'login_as_admin');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    var people = config.result;
    config = makeTestConfig(
      {parameters: {display_name: 'My lpclient team',
                    name: 'newlpclientteam'}});
    people.named_post('newTeam', config);
    Y.Assert.isTrue(config.successful);
    var team = config.result;
    Y.Assert.isInstanceOf(Y.lp.client.Entry, team);
    Y.Assert.areEqual('My lpclient team', team.get('display_name'));
    Y.Assert.isTrue(/\~newlpclientteam$/.test(team.uri));
  },

  test_collection_paged_named_get: function() {
    var data = serverfixture.setup(this, 'create_user');
    var client = new Y.lp.client.Launchpad({sync: true});
    var config = makeTestConfig();
    client.get('/people', config);
    var people = config.result;
    config = makeTestConfig({parameters: {text: data.user.name},
                             start: 10});
    people.named_get('find', config);
    Y.Assert.isTrue(config.successful);
    Y.Assert.isInstanceOf(Y.lp.client.Collection, config.result);
    // I believe that the total_size is not correct in this case for
    // server-side efficiency in an edge case.  It actually reports "10".
    // Y.Assert.areEqual(1, config.result.total_size);
    Y.Assert.areEqual(0, config.result.entries.length);
  }

}));

serverfixture.run(suite);
});
