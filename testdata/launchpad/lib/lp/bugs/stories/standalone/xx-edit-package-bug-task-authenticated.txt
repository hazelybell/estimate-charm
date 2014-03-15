Any authenticated user can edit a source package bug task.

    >>> browser.addHeader("Authorization", "Basic no-priv@canonical.com:test")
    >>> browser.open(
    ...     "http://localhost:9000/ubuntu/+source/mozilla-firefox"
    ...     "/+bug/1/+editstatus")

    >>> status_control = browser.getControl(
    ...     name="ubuntu_mozilla-firefox.status")
    >>> status_control.value
    ['New']
    >>> status_control.value = ["Confirmed"]

    >>> browser.getControl(name="ubuntu_mozilla-firefox.actions.save").click()

    >>> browser.open(
    ...     "http://localhost:9000/ubuntu/+source/mozilla-firefox"
    ...     "/+bug/1/+editstatus")

    >>> status_control = browser.getControl(
    ...     name="ubuntu_mozilla-firefox.status")
    >>> status_control.value
    ['Confirmed']
    >>> status_control.value = ["New"]

    >>> browser.getControl(name="ubuntu_mozilla-firefox.actions.save").click()
