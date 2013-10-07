/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide information and actions on all bug subscriptions a person holds.
 *
 * @module bugs
 * @submodule subscription
 */

YUI.add('lp.bugs.subscription', function(Y) {

var namespace = Y.namespace('lp.bugs.subscription');

/**
 * These are the descriptions strings of what might be the cause of you
 * getting an email.
 */

var _BECAUSE_YOU_ARE = 'You receive emails about this bug because you are ';

/**
 * Store complete subscription 'reasons' for easier overriding and testing.
 *
 * Other 'reasons' are added to the object as required string components
 * are defined.
 */
var reasons = {
    NOT_SUBSCRIBED: "You are not subscribed to this bug.",
    NOT_PERSONALLY_SUBSCRIBED: (
        "You are not directly subscribed to this bug, " +
            "but you have other subscriptions."),
    MUTED_SUBSCRIPTION: "You have muted all your direct email from this bug."
};
namespace._reasons = reasons;

/* These are components for team participation. */
var _OF_TEAM = 'of the team {team}, which is ';
var _OF_TEAMS = 'of the teams {teams}, which are ';
var _BECAUSE_TEAM_IS = _BECAUSE_YOU_ARE + 'a member ' + _OF_TEAM;
var _ADMIN_BECAUSE_TEAM_IS = (
    _BECAUSE_YOU_ARE + 'a member and administrator ' + _OF_TEAM);
var _BECAUSE_TEAMS_ARE = _BECAUSE_YOU_ARE + 'a member ' + _OF_TEAMS;
var _ADMIN_BECAUSE_TEAMS_ARE = (
        _BECAUSE_YOU_ARE + 'a member and administrator ' + _OF_TEAMS);

/* These are the assignment variations. */
var _ASSIGNED = 'assigned to work on it.';
/* These are the actual strings to use. */
Y.mix(reasons, {
    YOU_ASSIGNED: _BECAUSE_YOU_ARE + _ASSIGNED,
    TEAM_ASSIGNED: _BECAUSE_TEAM_IS + _ASSIGNED,
    ADMIN_TEAM_ASSIGNED: _ADMIN_BECAUSE_TEAM_IS + _ASSIGNED,
    TEAMS_ASSIGNED: _BECAUSE_TEAMS_ARE + _ASSIGNED,
    ADMIN_TEAMS_ASSIGNED: _ADMIN_BECAUSE_TEAMS_ARE + _ASSIGNED
});

/* These are the direct subscription variations. */
var _SUBSCRIBED = 'directly subscribed to it.';
var _MAY_HAVE_BEEN_CREATED = ' This subscription may have been created ';
var _YOU_SUBSCRIBED = _BECAUSE_YOU_ARE + _SUBSCRIBED;

/* Now these are the actual options we use. */
Y.mix(reasons, {
    YOU_SUBSCRIBED: _YOU_SUBSCRIBED,
    YOU_REPORTED: (_YOU_SUBSCRIBED + _MAY_HAVE_BEEN_CREATED +
                    'when you reported the bug.'),
    YOU_SUBSCRIBED_BUG_SUPERVISOR: (
        _YOU_SUBSCRIBED + _MAY_HAVE_BEEN_CREATED +
            'because the bug was private and you are a bug supervisor.'),
    TEAM_SUBSCRIBED: _BECAUSE_TEAM_IS + _SUBSCRIBED,
    ADMIN_TEAM_SUBSCRIBED: _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED,
    TEAMS_SUBSCRIBED: _BECAUSE_TEAMS_ARE + _SUBSCRIBED,
    ADMIN_TEAMS_SUBSCRIBED: _ADMIN_BECAUSE_TEAMS_ARE + _SUBSCRIBED
});

/* These are the duplicate bug variations. */
var _SUBSCRIBED_TO_DUPLICATE = (
    'a direct subscriber to bug {duplicate_bug}, which is marked as a ' +
        'duplicate of this bug, {bug_id}.');
var _SUBSCRIBED_TO_DUPLICATES = (
    'a direct subscriber to bugs {duplicate_bugs}, which are marked as ' +
        'duplicates of this bug, {bug_id}.');
/* These are the actual strings to use. */
Y.mix(reasons, {
    YOU_SUBSCRIBED_TO_DUPLICATE: _BECAUSE_YOU_ARE + _SUBSCRIBED_TO_DUPLICATE,
    YOU_SUBSCRIBED_TO_DUPLICATES: (
        _BECAUSE_YOU_ARE + _SUBSCRIBED_TO_DUPLICATES),
    TEAM_SUBSCRIBED_TO_DUPLICATE: _BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATE,
    TEAM_SUBSCRIBED_TO_DUPLICATES: (
        _BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATES),
    ADMIN_TEAM_SUBSCRIBED_TO_DUPLICATE: (
        _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATE),
    ADMIN_TEAM_SUBSCRIBED_TO_DUPLICATES: (
        _ADMIN_BECAUSE_TEAM_IS + _SUBSCRIBED_TO_DUPLICATES)
});

/* These are the owner variations. */
var _OWNER = (
    "the owner of {pillar}, which has no bug supervisor.");
/* These are the actual strings to use. */
Y.mix(reasons, {
    YOU_OWNER: _BECAUSE_YOU_ARE + _OWNER,
    TEAM_OWNER: _BECAUSE_TEAM_IS + _OWNER,
    ADMIN_TEAM_OWNER: _ADMIN_BECAUSE_TEAM_IS + _OWNER
});

/* These are the actions */

/**
 * This takes an array of ObjectLinks and a url_suffix, and returns a new
 * array of new ObjectLinks based on the input array, but with the suffix
 * appended to each original ObjectLink's url.
 */
function add_url_element_to_links(links, url_suffix) {
    var result = [];
    var index;
    for (index = 0; index < links.length; index++) {
        var original = links[index];
        result.push(ObjectLink(
            original.self, original.title, original.url + url_suffix));
    }
    return result;
}
namespace._add_url_element_to_links = add_url_element_to_links;

function lp_client() {
    // This is a hook point for tests.
    if (!Y.Lang.isValue(namespace._lp_client)) {
        namespace._lp_client = new Y.lp.client.Launchpad();
    }
    return namespace._lp_client;
}

/**
 * Helper to find the appropriate link text and get a list of
 * subscriptions that need to be unsubscribed for duplicate
 * subscriptions for a person/team.
 */
function get_unsubscribe_duplicates_text_and_subscriptions(args) {
    var text;
    var subscriptions = [];
    var index;
    if (Y.Lang.isValue(args.teams)) {
        // Unsubscribe team.

        // There should never be more than one team.
        if (args.teams.length !== 1) {
            Y.error('We can only unsubscribe a single team from ' +
                    'multiple duplicate bugs.');
        }
        // Collect all pairs of (team, dupe-bug) that need to be
        // unsubscribed.
        for (index = 0; index < args.bugs.length; index++) {
            subscriptions.push({
                subscriber: args.teams[0].self.self_link,
                bug: args.bugs[index].self.self_link
            });
        }
        text = choose_by_number(
            args.bugs.length,
            'Unsubscribe this team from the duplicate',
            'Unsubscribe this team from all duplicates');
    } else {
        // Unsubscribe person.

        // Collect all pairs of (team, dupe-bug) that need to be
        // unsubscribed.
        for (index = 0; index < args.bugs.length; index++) {
            subscriptions.push({
                subscriber: LP.links.me,
                bug: args.bugs[index].self.self_link
            });
        }
        text = choose_by_number(
            args.bugs.length,
            'Unsubscribe yourself from the duplicate',
            'Unsubscribe yourself from all duplicates');
    }
    return {
        text: text,
        subscriptions: subscriptions
    };
}
namespace._get_unsubscribe_duplicates_text_and_subscriptions =
        get_unsubscribe_duplicates_text_and_subscriptions;

/**
 * Helper to find the appropriate link text and get a list of
 * subscriptions that need to be unsubscribed for team subscriptions.
 */
function get_team_unsubscribe_text_and_subscriptions(args) {
    var subscriptions = [];
    var index;
    var text = choose_by_number(args.teams.length,
                                'Unsubscribe this team',
                                'Unsubscribe all of these teams');
    for (index = 0; index < args.teams.length; index++) {
        subscriptions.push({
            subscriber: args.teams[index].self.self_link,
            bug: LP.cache.context.bug_link
        });
    }
    return {
        text: text,
        subscriptions: subscriptions
    };
}
namespace._get_team_unsubscribe_text_and_subscriptions =
        get_team_unsubscribe_text_and_subscriptions;

/**
 * Returns a link node with on-click handler that unsubscribes all
 * subscriptions listed in `subscriptions` and link text set to `text`.
 */
function get_node_for_unsubscribing(text, subscriptions) {
    var node = Y.Node.create(
        '<a href="#" class="sprite modify remove js-action"></a>');
    var client = lp_client();
    var handler = new Y.lp.client.ErrorHandler();

    node.set('text', text);

    handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(node, error_msg);
    };
    handler.clearProgressUI = function () {
        node.replaceClass('spinner', 'remove');
    };

    node.on('click', function (e) {
        e.halt();
        var callback;
        callback = function () {
            if (subscriptions.length > 0) {
                // Fire off another unsubscribe call.
                var subscription = subscriptions.pop();
                var config = {
                    on: {success: callback,
                         failure: handler.getFailureHandler()},
                    parameters: {person: subscription.subscriber}
                };
                client.named_post(
                    subscription.bug,
                    'unsubscribe',
                    config);
            } else {
                // We are done.  Remove the parent node.
                node.replaceClass('spinner', 'remove');
                var container = node.ancestor(
                    '.subscription-description');
                var anim = Y.lp.ui.effects.slide_in(container);
                anim.on('end', function () {
                    container.remove();
                });
                anim.run();
            }
        };
        node.replaceClass('remove', 'spinner');
        callback();
    });

    return node;

}
namespace._get_node_for_unsubscribing = get_node_for_unsubscribing;

var actions = {
    CHANGE_ASSIGNEES: function () {
        return Y.Node.create('<a>Change assignees for this bug</a>')
            .set('href', LP.cache.context.web_link);
    },
    UNSUBSCRIBE_DUPLICATES: function (args) {
        var data = get_unsubscribe_duplicates_text_and_subscriptions(args);
        return get_node_for_unsubscribing(data.text, data.subscriptions);
    },
    CHANGE_TEAM_SUBSCRIPTIONS: function (args) {
        // TODO: add the ability to change notification level.
        var data = get_team_unsubscribe_text_and_subscriptions(args);
        return get_node_for_unsubscribing(data.text, data.subscriptions);
    },
    SET_BUG_SUPERVISOR: function (args) {
        return Y.Node.create('<a></a>')
            .set('text', 'Set the bug supervisor for ' + args.pillar.title)
            .set('href', args.pillar.web_link + '/+bugsupervisor');
    },
    CONTACT_TEAMS: function (args) {
        var node = Y.Node.create('<span></span>');
        node.set(
            'innerHTML',
            safely_render_description(
                {reason: 'Contact {teams} to request the administrators '+
                          'make a change',
                 vars: {
                    teams: add_url_element_to_links(
                        args.teams, '/+contactuser')}}));
        return node;
    }
};
namespace._actions = actions;

/**
 * Return appropriate object based on the number.
 *
 * @method choose_by_number.
 * @param {Integer} number Number used in the string.
 * @param {Object} singular Object to return when number == 1.
 * @param {Object} plural Object to return when number != 1.
 */
function choose_by_number(number, singular, plural) {
    if (number === 1) {
        return singular;
    } else {
        return plural;
    }
}
namespace._choose_by_number = choose_by_number;

/**
 * Replaces textual references in `info` with actual objects from `cache`.
 *
 * This assumes that object references are specified with strings
 * starting with 'subscription-cache-reference', and are direct keys
 * for objects in `cache`.
 *
 * @param {Object} info Object to recursively look for references through.
 * @param {Object} cache Cache containing the objects indexed by their
 *                       references.
 */
function replace_textual_references(info, cache) {
    var key;
    for (key in info) {
        if (info.hasOwnProperty(key)) {
            switch (typeof info[key]){
                case "object":
                    replace_textual_references(info[key], cache);
                    break;
                case "string":
                    var ref_string = "subscription-cache-reference-";
                    if (info[key].substring(0, ref_string.length)
                        === ref_string) {
                        info[key] = cache[info[key]];
                    }
                break;
                default: break;
            }
        }
    }
}
namespace._replace_textual_references = replace_textual_references;

/**
 * ObjectLink class to unify link elements for better consistency.
 * Needed because some objects expose `title`, others expose `display_name`.
 */
ObjectLink = function(self, title, url) {
    return {
        self: self,
        title: title,
        url: url
    };
};

/**
 * Convert a context object to a { title, url } object for use in web pages.
 * Uses `display_name` and `web_link` attributes.
 * Additionally, accepts a string as well and returns it unmodified.
 */
function get_link_data(context) {
    // For testing, we take strings as well.
    if (typeof(context) === 'string') {
        return context;
    } else {
        return ObjectLink(context, context.display_name, context.web_link);
    }
}

/**
 * Convert a bug object to a { title, url } object for use in web pages.
 * Uses `id` and `web_link` attributes.
 * Additionally, accepts a string as well and returns it unmodified.
 */
function get_bug_link_data(bug) {
    // For testing, we take strings as well.
    if (typeof(bug) === 'string') {
        return bug;
    } else {
        return ObjectLink(bug, '#' + bug.id.toString(), bug.web_link);
    }
}

/**
 * Gather all team subscriptions and sort them by the role: member/admin.
 * Returns up to 2 different subscription records, one for all teams
 * a person is a member of, and another for all teams a person is
 * an admin for.
 * With one team in a subscription, variable `team` is set, and with more
 * than one, variable `teams` is set containing all the teams.
 */
function gather_subscriptions_by_role(
    category, team_config, admin_team_config) {
    var results = [],
        work_index,
        index,
        work = [{subscriptions: category.as_team_member,
                 config: team_config},
                {subscriptions: category.as_team_admin,
                 config: admin_team_config}];
    for (work_index = 0; work_index < work.length; work_index++) {
        var subscriptions = work[work_index].subscriptions;
        var config = work[work_index].config;
        if (subscriptions.length > 0) {
            var team_map = {};
            var teams = [];
            for (index = 0; index < subscriptions.length; index++) {
                var team_subscription = subscriptions[index],
                    team = team_subscription.principal,
                    key = team.web_link;
                key = Y.Lang.isValue(key) ? key : team; // For tests.
                if (!Y.Lang.isValue(team_map[key])) {
                    var link_data = get_link_data(team);
                    team_map[team.web_link] = link_data;
                    teams.push(link_data);
                }
            }
            var sub = choose_by_number(
                subscriptions.length,
                { reason: config.singular,
                  vars: {
                      team: teams[0] } },
                { reason: config.plural,
                  vars: {
                      teams: teams } });
            sub.action = config.action;
            sub.args = {teams: teams};
            results.push(sub);
        }
    }

    return results;
}

/**
 * Gather subscription information for assignee.
 */
function gather_subscriptions_as_assignee(category) {
    var subscriptions = [];
    var reasons = namespace._reasons;

    if (category.personal.length > 0) {
        subscriptions.push(
            { reason: reasons.YOU_ASSIGNED,
              vars: {},
              action: actions.CHANGE_ASSIGNEES });
    }

    // We add all the team assignments grouped by roles in the team.
    return subscriptions.concat(
        gather_subscriptions_by_role(
            category,
            {singular: reasons.TEAM_ASSIGNED,
             plural: reasons.TEAMS_ASSIGNED,
             action: actions.CONTACT_TEAMS},
            {singular: reasons.ADMIN_TEAM_ASSIGNED,
             plural: reasons.ADMIN_TEAMS_ASSIGNED,
             action: actions.CHANGE_ASSIGNEES}));
}
namespace._gather_subscriptions_as_assignee =
        gather_subscriptions_as_assignee;

/**
 * Adds a `subscription` to `subscriptions` if it's not in the list already.
 * Compares reason, action and all the `vars` from existing subscription.
 */
function add_subscription_to_set(subscriptions, subscription) {
    var index, sub;
    for (index = 0; index < subscriptions.length; index++) {
        sub = subscriptions[index];
        if (sub.reason === subscription.reason &&
            sub.action === subscription.action) {
            var are_vars_same = true;
            var param;
            for (param in sub.vars) {
                if (sub.vars.hasOwnProperty(param)) {
                    // We only check vars from the existing subscription.
                    // Theoretically, there could be a var on `subscription`
                    // not present on `sub`, but we're guarding against that
                    // with reason/action checks.
                    if (sub.vars[param].self
                            !== subscription.vars[param].self) {
                        are_vars_same = false;
                        break;
                    }
                }
            }
            if (are_vars_same) {
                return;
            }
        }
    }
    // We haven't found matching subscriptions, add it.
    subscriptions.push(subscription);
}

/**
 * Gather subscription information for implicit bug supervisor.
 */
function gather_subscriptions_as_supervisor(category) {
    var subscriptions = [];
    var reasons = namespace._reasons;
    var index, team_subscription, team_link;

    for (index = 0; index < category.personal.length; index++) {
        var subscription = category.personal[index];
        add_subscription_to_set(subscriptions, {
            reason: reasons.YOU_OWNER,
            vars: {
                pillar: get_link_data(subscription.pillar)
            },
            action: actions.SET_BUG_SUPERVISOR,
            args: {pillar: subscription.pillar}
        });
    }

    for (index = 0; index < category.as_team_member.length; index++) {
        team_subscription = category.as_team_member[index];
        team_link = get_link_data(team_subscription.principal);
        add_subscription_to_set(subscriptions, {
            reason: reasons.TEAM_OWNER,
            vars: {
                team: team_link,
                pillar: get_link_data(team_subscription.pillar)
            },
            action: actions.CONTACT_TEAMS,
            args: {teams: [team_link]}
        });
    }

    for (index = 0; index < category.as_team_admin.length; index++) {
        team_subscription = category.as_team_admin[index];
        add_subscription_to_set(subscriptions, {
            reason: reasons.ADMIN_TEAM_OWNER,
            vars: {
                team: get_link_data(team_subscription.principal),
                pillar: get_link_data(team_subscription.pillar)
            },
            action: actions.SET_BUG_SUPERVISOR,
            args: {pillar: team_subscription.pillar}
        });
    }

    return subscriptions;
}
namespace._gather_subscriptions_as_supervisor =
        gather_subscriptions_as_supervisor;

function gather_dupe_subscriptions_by_team(team_subscriptions,
                                           singular, plural, action) {
    var subscriptions = [];
    var index;
    var subscription, sub;
    var added_bug;
    var team_dupes_idx, team_dupes;

    // Collated list of { team: ..., bugs: []} records.
    var dupes_by_teams = [];
    for (index = 0; index < team_subscriptions.length; index++) {
        subscription = team_subscriptions[index];
        // Find the existing team reference.
        added_bug = false;
        for (team_dupes_idx = 0; team_dupes_idx < dupes_by_teams.length;
             team_dupes_idx++) {
            team_dupes = dupes_by_teams[team_dupes_idx];
            if (team_dupes.team === subscription.principal) {
                team_dupes.bugs.push(get_bug_link_data(subscription.bug));
                added_bug = true;
                break;
            }
        }
        if (!added_bug) {
            dupes_by_teams.push({
                team: subscription.principal,
                bugs: [get_bug_link_data(subscription.bug)]
            });
        }
    }
    for (team_dupes_idx = 0; team_dupes_idx < dupes_by_teams.length;
         team_dupes_idx++) {
        team_dupes = dupes_by_teams[team_dupes_idx];
        sub = choose_by_number(
            team_dupes.bugs.length,
            { reason: singular,
              vars: { duplicate_bug: team_dupes.bugs[0],
                      team: get_link_data(team_dupes.team) }},
            { reason: plural,
              vars: { duplicate_bugs: team_dupes.bugs,
                      team: get_link_data(team_dupes.team) }});
        sub.action = action;
        sub.args = { teams: [sub.vars.team],
                     bugs: team_dupes.bugs };
        subscriptions.push(sub);
    }
    return subscriptions;
}

/**
 * Gather subscription information from duplicate bug subscriptions.
 */
function gather_subscriptions_from_duplicates(category) {
    var subscriptions = [];
    var reasons = namespace._reasons;
    var index, dupes, subscription;

    if (category.personal.length > 0) {
        dupes = [];
        for (index = 0; index < category.personal.length; index++) {
            subscription = category.personal[index];
            dupes.push(
                get_bug_link_data(subscription.bug));
        }
        var sub = choose_by_number(
            dupes.length,
            { reason: reasons.YOU_SUBSCRIBED_TO_DUPLICATE,
              vars: { duplicate_bug: dupes[0] }},
            { reason: reasons.YOU_SUBSCRIBED_TO_DUPLICATES,
              vars: { duplicate_bugs: dupes }});
        sub.action = actions.UNSUBSCRIBE_DUPLICATES;
        sub.args = { bugs: dupes };
        subscriptions.push(sub);
    }

    // Get subscriptions as team member, grouped by teams.
    subscriptions = subscriptions.concat(
        gather_dupe_subscriptions_by_team(
            category.as_team_member,
            reasons.TEAM_SUBSCRIBED_TO_DUPLICATE,
            reasons.TEAM_SUBSCRIBED_TO_DUPLICATES,
            actions.CONTACT_TEAMS));

    // Get subscriptions as team admin, grouped by teams.
    subscriptions = subscriptions.concat(
        gather_dupe_subscriptions_by_team(
            category.as_team_admin,
            reasons.ADMIN_TEAM_SUBSCRIBED_TO_DUPLICATE,
            reasons.ADMIN_TEAM_SUBSCRIBED_TO_DUPLICATES,
            actions.UNSUBSCRIBE_DUPLICATES));

    return subscriptions;
}
namespace._gather_subscriptions_from_duplicates =
        gather_subscriptions_from_duplicates;

/**
 * Gather subscription information from direct team subscriptions.
 */
function gather_subscriptions_through_team(category) {
    var reasons = namespace._reasons;
    return gather_subscriptions_by_role(
        category,
        {singular: reasons.TEAM_SUBSCRIBED,
         plural: reasons.TEAMS_SUBSCRIBED,
         action: actions.CONTACT_TEAMS},
        {singular: reasons.ADMIN_TEAM_SUBSCRIBED,
         plural:reasons.ADMIN_TEAMS_SUBSCRIBED,
         action: actions.CHANGE_TEAM_SUBSCRIPTIONS});
}
namespace._gather_subscriptions_through_team =
        gather_subscriptions_through_team;

/**
 * Gather all non-direct subscriptions into a list.
 */
function gather_nondirect_subscriptions(info) {
    var subscriptions = [];

    return subscriptions
        .concat(gather_subscriptions_as_assignee(info.as_assignee))
        .concat(gather_subscriptions_from_duplicates(info.from_duplicate))
        .concat(gather_subscriptions_through_team(info.direct))
        .concat(gather_subscriptions_as_supervisor(info.as_owner));

}

// This mapping contains the IDs of elements that will be made visible if they
// apply to the current bug.
var action_ids = {
    mute: 'mute-direct-subscription',
    unmute: 'unmute-direct-subscription',
    subscribe_all: 'select-direct-subscription-discussion',
    subscribe_metadata: 'select-direct-subscription-metadata',
    subscribe_closed: 'select-direct-subscription-lifecycle',
    subscribe_only_metadata: 'select-only-direct-subscription-metadata',
    subscribe_only_closed: 'select-only-direct-subscription-lifecycle',
    unsubscribe: 'remove-direct-subscription',
    unsubscribe_with_warning: 'remove-direct-subscription-with-warning'
};
namespace._action_ids = action_ids;

/**
 * Get direct subscription information.
 */
function get_direct_subscription_information(info) {
    var reason;
    var reasons = namespace._reasons;
    var reductions = [];
    var increases = [];
    if (info.count === 0 && !has_structural_subscriptions()) {
        // The user has no subscriptions at all.
        reason = reasons.NOT_SUBSCRIBED;
        increases.push(action_ids.subscribe_all);
        increases.push(action_ids.subscribe_metadata);
        increases.push(action_ids.subscribe_closed);
    } else if (info.muted) {
        // The user has a muted direct subscription.
        reason = reasons.MUTED_SUBSCRIPTION;
        increases.push(action_ids.unmute);
    } else if (info.direct.personal.length > 0) {
        // The user has a direct personal subscription.
        if (info.direct.personal.length > 1) {
            Y.error(
                'Programmer error: a person should not have more than ' +
                'one direct personal subscription.');
        }
        var subscription = info.direct.personal[0];
        var bug = subscription.bug;
        if (subscription.principal_is_reporter) {
            reason = reasons.YOU_REPORTED;
        } else if (bug['private']) {
            reason = reasons.YOU_SUBSCRIBED_BUG_SUPERVISOR;
        } else {
            reason = reasons.YOU_SUBSCRIBED;
        }
        reductions.push(action_ids.mute);
        switch (subscription.subscription.bug_notification_level) {
            case 'Discussion':
                reductions.push(action_ids.subscribe_only_metadata);
                reductions.push(action_ids.subscribe_only_closed);
                break;
            case 'Details':
                increases.push(action_ids.subscribe_all);
                reductions.push(action_ids.subscribe_only_closed);
                break;
            case 'Lifecycle':
                increases.push(action_ids.subscribe_all);
                increases.push(action_ids.subscribe_metadata);
                break;
            default:
                Y.error('Programmer error: unknown bug notification level: '+
                        subscription.subscription.bug_notification_level);
        }
        if (info.count > 1) {
            // The user has a non-personal subscription as well as a direct
            // personal subscription.
            reductions.push(action_ids.unsubscribe_with_warning);
        } else {
            // The user just has the direct personal subscription.
            reductions.push(action_ids.unsubscribe);
        }

    } else {
        // No direct subscriptions, but there are other
        // subscriptions (because info.count != 0).
        reason = reasons.NOT_PERSONALLY_SUBSCRIBED;
        reductions.push(action_ids.mute);
        reductions.push(action_ids.subscribe_only_metadata);
        reductions.push(action_ids.subscribe_only_closed);
        increases.push(action_ids.subscribe_all);
    }
    return {reason: reason, reductions: reductions, increases: increases};
}
namespace._get_direct_subscription_information =
        get_direct_subscription_information;

/**
 * Returns an anchor element HTML for an ObjectLink element.
 * It safely encodes the `title` and `url` elements to avoid any XSS vectors.
 *
 * @method get_objectlink_html
 * @param {Object} element ObjectLink element or a simple string.
 * @returns {String} HTML for the A element representing passed in
 *     ObjectLink `element`.  If `element` is a string, return it unmodified.
 */
function get_objectlink_html(element) {
    if (Y.Lang.isString(element)) {
        return element;
    } else if (Y.Lang.isObject(element)) {
        if (element.url === undefined && element.title === undefined) {
            Y.error('Not a proper ObjectLink.');
        }
        var node = Y.Node.create('<div></div>');
        node.appendChild(
            Y.Node.create('<a></a>')
                .set('href', element.url)
                .set('text', element.title));
        var text = node.get('innerHTML');
        node.destroy(true);
        return text;
    }
}
namespace._get_objectlink_html = get_objectlink_html;

/**
 * Array sort function for objects sorting them by their `title` property.
 */
function sort_by_title(a, b) {
    return ((a.title === b.title) ? 0 :
            ((a.title > b.title) ? 1 : -1));
}

/**
 * Renders the description in a safe manner escaping HTML as appropriate.
 *
 * @method safely_render_description
 * @param {Object} subscription Object containing the string `reason` and
 *            object `vars` containing variables to be replaced in `reason`.
 * @param {Object} additional_vars Objects containing additional, global
 *            variables to also be replaced if not overridden.
 * @returns {String} `reason` with all {var} occurrences replaced with
 *            appropriate subscription.vars[var] values.
 */
function safely_render_description(subscription, additional_vars) {
    function var_replacer(key, vars) {
        var index, final_element, text_elements;
        if (vars !== undefined) {
            if (Y.Lang.isArray(vars)) {
                vars.sort(sort_by_title);
                // This can handle plural or singular.
                final_element = get_objectlink_html(vars.pop());
                text_elements = [];
                for (index in vars) {
                    if (vars.hasOwnProperty(index)) {
                        text_elements.push(get_objectlink_html(vars[index]));
                    }
                }
                if (text_elements.length > 0) {
                    return text_elements.join(', ') + ' and ' + final_element;
                } else {
                    return final_element;
                }
            } else {
                return get_objectlink_html(vars);
            }
        } else {
            if (Y.Lang.isObject(additional_vars) &&
                additional_vars.hasOwnProperty(key)) {
                return get_objectlink_html(additional_vars[key]);
            }
        }
    }
    var replacements = {}; 
    for (var property in subscription.vars) {
        replacements[property] = var_replacer(
            undefined, subscription.vars[property]);
    }
    for (var property in additional_vars) {
        replacements[property] = var_replacer(
            property, additional_vars[property]);
    }
    return Y.Lang.sub(subscription.reason, replacements);
}
namespace._safely_render_description = safely_render_description;

/**
 * This is a simple helper function for the *_action functions below.  It
 * takes an id and returns a Y.Node div with that id.
 */
function make_action(id) {
    return Y.Node.create('<div/>')
        .addClass('hidden')
        .set('id', id);
}

/**
 * Return a node for muting the bug.
 */
function mute_action() {
    return make_action(action_ids.mute)
        .append(
            make_action_link(
                'mute all emails from this bug',
                 'mute', 'mute', {}));
}
namespace._mute_action = mute_action;

/**
 * Return a node for unmuting the bug.
 */
function unmute_action() {
    return make_action(action_ids.unmute)
        .append(
            make_action_link(
                'unmute emails from this bug',
                 'unmute', 'unmute', {}));
}
namespace._unmute_action = unmute_action;

/**
 * Return a node for subscribing to all emails from the bug.
 */
function subscribe_all_action() {
    return make_action(action_ids.subscribe_all)
        .append(make_subscribe_link(
            'receive all emails about this bug', 'Discussion'));
}
namespace._subscribe_all_action = subscribe_all_action;

/**
 * Return a node for subscribing to emails from this bug other than comments.
 */
function subscribe_metadata_action() {
    return make_action(action_ids.subscribe_metadata)
        .append(make_subscribe_link(
            'receive all emails about this bug except comments', 'Details'));
}
namespace._subscribe_metadata_action = subscribe_metadata_action;

/**
 * Return a node for subscribing to emails about this bug closing.
 */
function subscribe_closed_action() {
    return make_action(action_ids.subscribe_closed)
        .append(make_subscribe_link(
            'only receive email when this bug is closed', 'Lifecycle'));
}
namespace._subscribe_closed_action = subscribe_closed_action;

/**
 * Return a node for reducing emails received from this bug to eliminate
 * comments.  This is functionally identical to subscribe_metadata_action,
 * but has different text and is presented as a reduction, not an increase.
 */
function subscribe_only_metadata_action() {
    return make_action(action_ids.subscribe_only_metadata)
        .append(make_subscribe_link(
            'stop receiving comments from this bug', 'Details'));
}
namespace._subscribe_only_metadata_action = subscribe_only_metadata_action;

/**
 * Return a node for reducing emails received from this bug to eliminate
 * everything but closing notifications.  This is functionally identical to
 * subscribe_closed_action, but has different text and is presented as a
 * reduction, not an increase.
 */
function subscribe_only_closed_action() {
    return make_action(action_ids.subscribe_only_closed)
        .append(make_subscribe_link(
            'only receive email when this bug is closed', 'Lifecycle'));
}
namespace._subscribe_only_closed_action = subscribe_only_closed_action;

/**
 * Return a node for unsubscribing to emails about this bug.
 */
function unsubscribe_action() {
    return make_action(action_ids.unsubscribe)
        .append(
            make_action_link(
                'unsubscribe from this bug',
                 'remove', 'unsubscribe', {}));
}
namespace._unsubscribe_action = unsubscribe_action;

/**
 * Return a node for unsubscribing to emails about this bug.  This is
 * functionally identical to unsubscribe_action, but has different text and
 * includes a warning that unsubscribing may not stop all emails.  This node
 * is intended to be used if there are other, non-direct non-personal
 * subscriptions that will cause the person to receive emails.
 */
function unsubscribe_with_warning_action() {
    return make_action(action_ids.unsubscribe_with_warning)
        .append(
            Y.Node.create('<span/>')
                .set('text', 'You can also '))
        .append(
            make_action_link(
                'unsubscribe from this bug',
                 'remove', 'unsubscribe', {}))
        .append(
            Y.Node.create('<span/>')
                .set('text',
                     '.  However, you also have other subscriptions to '+
                     'this bug that may send you email once you have '+
                     'unsubscribed.'));
}
namespace._unsubscribe_with_warning_action = unsubscribe_with_warning_action;

/**
 * Makes links for subscribing actions.
 */
function make_subscribe_link(text, level) {
    return make_action_link(
        text,
        'edit',
        'subscribe',
        {person: LP.links.me, level: level}
    );
}

function make_action_link_function (
    node, sprite_class, method_name, handler, parameters, client) {
    // Performs the heavy lifting for make_action_link.
    var config = {
        on: {success:
            function (maybe_sub) {
                node.replaceClass('spinner', sprite_class);
                var info = LP.cache.bug_subscription_info;
                var old = info.direct.personal[0];
                if (Y.Lang.isValue(maybe_sub)) {
                    // Set the subscription in info and in cache.
                    var sub = maybe_sub.getAttrs();
                    if (Y.Lang.isValue(old)) {
                        info.direct.personal[0].subscription = sub;
                    } else {
                        // We don't have enough information to calculate
                        // everything on the fly. Luckily, we don't need
                        // most of it, and we think it is alright to not
                        // include the extra information about
                        // principal_is_reporter and bug_supervisor_pillars.
                        info.direct.personal.push(
                            {principal: {},
                            bug: {},
                            subscription: sub,
                            principal_is_reporter: false,
                            bug_supervisor_pillars: []
                           });
                       info.direct.count += 1;
                       info.count += 1;
                   }
               } else {
                   if (Y.Lang.isValue(old)) {
                       info.direct.personal.pop();
                       info.direct.count -= 1;
                       info.count -= 1;
                   }
               }
               if (method_name === 'mute') {
                   info.muted = true;
               } else if (method_name === 'unmute') {
                   info.muted = false;
               }
               reveal_direct_description_actions(
                   Y.one('#direct-subscription'),
                   get_direct_subscription_information(info));
            },
        failure: handler.getFailureHandler()},
        parameters: parameters
    };
    node.replaceClass(sprite_class, 'spinner');
    client.named_post(LP.cache.context.bug_link, method_name, config);
}

/**
 * Makes links for all kinds of actions.
 *
 * The link will be constructed to have an icon followed by text with
 * it all part of the <a> link.
 *
 * @param {String} text Text of the link to be created.
 * @param {String} sprite_class Name of the sprite to use for an icon.
 * @param {String} method_name API method to call on the bug_link when the
 *            link is clicked.
 * @param {Object} parameters Dict of parameters to be passed to method_name.
 */
function make_action_link(text, sprite_class, method_name, parameters) {
    var node = Y.Node.create('<a/>')
        .set('text', text)
        .set('href', '#') // Makes the mouse arrow change into a hand.
        .addClass('sprite')
        .addClass('modify')
        .addClass(sprite_class)
        .addClass('js-action');
    var client = lp_client();
    var handler = new Y.lp.client.ErrorHandler();

    handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(node, error_msg);
    };
    handler.clearProgressUI = function () {
        node.replaceClass('spinner', sprite_class);
    };
    node.on(
        'click',
        function (e) {
            e.halt();
            var method_call = function() {
                make_action_link_function(
                    node, sprite_class, method_name, handler, parameters,
                    client);
            };
            // If this a private bug, and the user is unsubscribing
            // themselves, give them a warning.
            if (
                method_name === 'unsubscribe' &&
                Y.Lang.isBoolean(LP.cache.bug_is_private) &&
                LP.cache.bug_is_private) {
                var content = [
                    '<p>You will not have access to this bug or any of ',
                    'its pages if you unsubscribe. If you want to stop ',
                    'emails, choose the "Mute bug mail" option.</p><p>Do ',
                    'you really want to unsubscribe from this bug?</p>'
                    ].join('');
                var ns = Y.lp.app.confirmationoverlay;
                var co = new ns.ConfirmationOverlay({
                    submit_fn: method_call,
                    form_content: content,
                    headerContent: 'Unsubscribe from this bug',
                    submit_text: 'Unsubscribe'
                });
                co.show();
            } else {
                method_call();
            }
        });
    return node;
}
namespace._make_action_link = make_action_link;

function border_box(title, content_div) {
    return Y.Node.create('<div/>')
        .addClass('hidden')
        .setStyle('border', '1px solid #ddd')
        .setStyle('padding', '0 1em 1em 1em')
        .setStyle('marginTop', '1em')
        .append(Y.Node.create('<span/>')
            .setStyle('backgroundColor', '#fff')
            .setStyle('float', 'left')
            .setStyle('marginTop', '-0.8em')
            .setStyle('padding', '0 0.5em')
            .set('text', title))
        .append(content_div
            .setStyle('clear', 'both')
            .setStyle('padding', '1em 0 0 1em'));
}

/**
 * Creates a node to store the direct subscription information.
 *
 * @returns {Object} Y.Node with the ID of 'direct-description' with the
 *     expected structure for reason, reducing actions and increasing actions.
 */
function get_direct_description_node() {
    var less_email_title = 'If you don\'t want to receive emails about '+
        'this bug you can';
    var more_email_title = 'If you want to receive more emails about '+
        'this bug you can';
    var direct_node = Y.Node.create('<div/>')
        .set('id', 'direct-subscription')
        // Make element for reason's text.
        .append(Y.Node.create('<div/>')
            .setStyle('paddingBottom', '1.0em')
            .addClass('reason'))
        // Make border box for actions that reduce email.
        .append(border_box(less_email_title, Y.Node.create('<div/>')
                .append(mute_action())
                .append(subscribe_only_metadata_action())
                .append(subscribe_only_closed_action())
                .append(unsubscribe_action()))
            .addClass('reductions'))
        // Make border box for actions that increase email.
        .append(border_box(more_email_title, Y.Node.create('<div/>')
                .append(unmute_action())
                .append(subscribe_all_action())
                .append(subscribe_metadata_action())
                .append(subscribe_closed_action()))
            .addClass('increases'))
        // Add the unsubscribe action for when they have other subscriptions.
        .append(unsubscribe_with_warning_action());
    return direct_node;
}
namespace._get_direct_description_node = get_direct_description_node;

/**
 * Mutates direct subscription node to render the appropriate information.
 *
 * @param {Object} direct_node The Y.Node as generated by
 *     get_direct_description_node.
 * @param {Object} direct_info An object as returned from
 *     get_direct_subscription_information.  Should have a text `reason`,
 *     a `reductions` list of reduction action ids to reveal, and a
 *     `increases` list of increasing action ids to reveal.
 */
function reveal_direct_description_actions(direct_node, direct_info) {
    var i;
    var key;
    direct_node.one('.reason').set('text', direct_info.reason);
    // Hide all actions.  This is particularly important when we redraw
    // actions after a successful direct subscription action.  After we hide
    // these, we will reveal the ones we want, immediately below.
    for (key in action_ids) {
        if (action_ids.hasOwnProperty(key)) {
            direct_node.one('#'+action_ids[key]).addClass('hidden');
        }
    }
    if (direct_info.reductions.length !== 0) {
        // If there are any actions the user can take, unhide the actions box
        // and then unhide the specific actions that they should see.
        direct_node.one('.reductions').removeClass('hidden');
        for (i=0; i<direct_info.reductions.length; i++) {
            direct_node.one('#'+direct_info.reductions[i])
                .removeClass('hidden');
        }
    } else {
        direct_node.one('.reductions').addClass('hidden');
    }

    if (direct_info.increases.length !== 0) {
        // If there are any actions the user can take, unhide the actions box
        // and then unhide the specific actions that they should see.
        direct_node.one('.increases').removeClass('hidden');
        for (i=0; i<direct_info.increases.length; i++) {
            direct_node.one('#'+direct_info.increases[i])
                .removeClass('hidden');
        }
    } else {
        direct_node.one('.increases').addClass('hidden');
    }
}
namespace._reveal_direct_description_actions =
    reveal_direct_description_actions;

/**
 * Creates a node to store single subscription description.
 *
 * @param {Object} subscription Object containing `reason` and `vars`
 *     to be substituted into `reason` with safely_render_description.
 * @param {Object} extra_data Extra variables to substitute.
 * @returns {Object} Y.Node with the class 'bug-subscription-description'
 *     and textual description in a separate node with
 *     class 'description-text'.
 */
function get_single_description_node(subscription, extra_data) {
    var node = Y.Node.create('<div />')
        .setStyle('display', 'table')
        .setStyle('width', '100%')
        .addClass('subscription-description');
    node.appendChild(
        Y.Node.create('<div />')
            .addClass('description-text')
            .setStyle('display', 'table-cell')
            .setStyle('width', '60%')
            .set('innerHTML',
                 safely_render_description(subscription, extra_data)));
    var action_node = subscription.action(subscription.args);
    if (Y.Lang.isValue(action_node)) {
        var div = Y.Node.create('<div />');
        div.appendChild(action_node);
        div.setStyle('display', 'table-cell')
           .setStyle('paddingLeft', '5em')
           .setStyle('text-align', 'right');
        node.appendChild(div);
    }
    return node;
}
namespace._get_single_description_node = get_single_description_node;

/**
 * Creates a node to store "other" subscriptions information.
 * "Other" means any bug subscriptions which are not personal and direct.
 *
 * @param {Object} info LP.cache.bug_subscription_info object.
 * @param {Object} extra_data Additional global variables to substitute
 *     in strings.  Passed directly through to safely_render_description().
 * @returns {Object} Y.Node with the ID of 'other-subscriptions' and
 *     add descriptions of each subscription as a separate node.
 */
function get_other_descriptions_node(info, extra_data) {
    var subs = gather_nondirect_subscriptions(info);
    var index;
    if (subs.length > 0 || has_structural_subscriptions()) {
        var node = Y.Node.create('<div></div>')
            .set('id', 'other-subscriptions');
        var header = Y.Node.create('<div></div>')
            .set('id', 'other-subscriptions-header');
        var header_link = Y.Node.create('<a></a>')
            .set('href', '#')
            .set('text', 'Other subscriptions');
        header.appendChild(header_link);
        node.appendChild(header);
        var list = Y.Node.create('<div></div>')
            .set('id', 'other-subscriptions-list');
        node.appendChild(list);

        setup_slider(list, header_link);

        for (index = 0; index < subs.length; index++) {
            list.appendChild(
                get_single_description_node(subs[index], extra_data));
        }

        return node;
    } else {
        return undefined;
    }
}
namespace._get_other_descriptions_node = get_other_descriptions_node;

/**
 * Are there any structural subscriptions that need to be rendered.
 */
function has_structural_subscriptions() {
    return (LP.cache.subscription_info &&
            LP.cache.subscription_info.length > 0);
}

/**
 * Sets up a slider that slides the `body` in and out when `header`
 * is clicked.
 */
function setup_slider(body, header) {
    // Hide the widget body contents.
    body.addClass('lazr-closed');
    body.setStyle('display', 'none');

    // Ensure that the widget header uses the correct sprite icon
    // and gets the styling for javascript actions applied.
    header.addClass('sprite');
    header.addClass('treeCollapsed');
    header.addClass('js-action');

    var slide;
    function toggle_body_visibility(e) {
        e.halt();
        if (!slide) {
            slide = Y.lp.ui.effects.slide_out(body);
            header.replaceClass('treeCollapsed', 'treeExpanded');
        } else {
            slide.set('reverse', !slide.get('reverse'));
            header.toggleClass('treeExpanded');
            header.toggleClass('treeCollapsed');
        }
        slide.stop();
        slide.run();
    }
    header.on('click', toggle_body_visibility);
}

/**
 * Add descriptions for all non-structural subscriptions to the page.
 *
 * @param {Object} config Object specifying the node to populate in
 *     `description_box` and allowing LP.cache.bug_subscription_info
 *     override with `subscription_info` property.
 */
function show_subscription_description(config) {
    // Allow tests to pass subscription_info directly in.
    var info = config.subscription_info || LP.cache.bug_subscription_info;
    // Replace subscription-cache-reference-* strings with actual
    // object references.
    replace_textual_references(info, LP.cache);

    var extra_data = {
        bug_id: '#' + info.bug_id.toString()
    };

    var content_node = Y.one(config.description_box);

    var direct_node = get_direct_description_node();
    reveal_direct_description_actions(
        direct_node,
        get_direct_subscription_information(info));
    content_node.appendChild(direct_node);

    var other_node = get_other_descriptions_node(info, extra_data);
    if (other_node !== undefined) {
        content_node.appendChild(other_node);
    }
}
namespace.show_subscription_description = show_subscription_description;

}, '0.1', {requires: [
    'dom', 'event', 'node', 'lang', 'lp.ui.effects', 'lp.app.errors',
    'lp.app.confirmationoverlay', 'lp.client'
]});
