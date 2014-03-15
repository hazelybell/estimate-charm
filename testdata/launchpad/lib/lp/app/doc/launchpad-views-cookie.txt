launchpad_views cookie
======================

The launchpad UI can remember the state of how a user chooses to view it.
The state is stored in a cookie. The cookie is set by the browser scripts
when the user chooses to show or hide an element of the page. Launchpad
can use the cookie state to not render parts of the page the user is
not interested in.

The get_launchpad_views function accepts the request.cookies object and
returns a dict of True or False values for the predefined keys.

    >>> from lp.app.browser.launchpad import get_launchpad_views
    >>> from lp.services.webapp.servers import LaunchpadTestRequest

    >>> def test_get_launchpad_views(cookie):
    ...     request = LaunchpadTestRequest(HTTP_COOKIE=cookie)
    ...     return get_launchpad_views(request.cookies)

get_launchpad_views sets the default values for the launchpad_views dict.
The cookie is not required.

    >>> launchpad_views = test_get_launchpad_views('')
    >>> launchpad_views['small_maps']
    True

    >>> launchpad_views = test_get_launchpad_views('other_cookie=key=value')
    >>> launchpad_views['small_maps']
    True

The value of 'false' for a key in the cookie is treated as False. 'false'
is the only explicit value accepted to change the state of a key.

    >>> launchpad_views = test_get_launchpad_views(
    ...     'launchpad_views=small_maps=false')
    >>> launchpad_views['small_maps']
    False

Any other value is treated as True because that is the default state.

    >>> launchpad_views = test_get_launchpad_views(
    ...     'launchpad_views=small_maps=true')
    >>> launchpad_views['small_maps']
    True

    >>> launchpad_views = test_get_launchpad_views(
    ...     'launchpad_views=small_maps=bogus')
    >>> launchpad_views['small_maps']
    True

Keys that are not predefined in get_launchpad_views are not accepted.

    >>> launchpad_views = test_get_launchpad_views(
    ...     'launchpad_views=bad_key=false')
    >>> launchpad_views['bad_key']
    Traceback (most recent call last):
     ...
    KeyError: ...

A corrupted or hacked cookie is ignored. The default values are used.

    >>> launchpad_views = test_get_launchpad_views(
    ...     'launchpad_views=small_maps=b=c&d')
    >>> launchpad_views['small_maps']
    True
