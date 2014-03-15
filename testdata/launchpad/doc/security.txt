Security Policy in Launchpad
============================

Zope 3 is a security-aware framework that makes it possible to develop complex
applications with security policies that closely resemble the reality that the
system is trying to model.

This document is about security policy in Launchpad.

Defining Permissions in Launchpad
---------------------------------

**NOTE: A new permission should only be defined if absolutely necessary, and
it should be considered thoroughly in a code review.**

Occassionally, you'll find yourself in a situation where the existing
permissions in Launchpad aren't enough for what you want. For example, as I
was writing this document I needed a permission I could attach to things to
provide policy for who can view a thing. That is, I wanted a permission called
launchpad.View.
A new permission (see the NOTE above) is defined in Launchpad in the file
lib/canonical/launchpad/permissions.zcml. So, to define the permission
launchpad.View, we'd add a line like this to that file:

    <permission id="launchpad.View" title="Viewing something"
      access_level="read" />


Defining Authorization Policies for Permissions
-----------------------------------------------

Once you've defined a permission, you'll probably want to define some logic
somewhere to express the authorization policy for that permission on a certain
interface.

In Launchpad, an authorization policy is expressed through a security adapter.
To define a security adapter for a given permission on an interface:

1. Define the adapter in lib/canonical/launchpad/security.py. Here's a simple
example of an adapter that authorizes only an object owner for the
launchpad.Edit permission on objects that implement the IHasOwner interface::

    class EditByOwner(AuthorizationBase):
        permission = 'launchpad.Edit'
        usedfor = IHasOwner

        def checkAuthenticated(self, person):
            """Authorize the object owner."""
            if person.id == self.obj.owner.id:
                return True

Read the IAuthorization interface to ensure that you've defined the adapter
appropriately.

2. Declare the permission on a given interface in a zcml file. So, for the
above adapter, here's how it's hooked up to IProduct, where IProduct is
protected with the launchpad.Edit permission::

    <class
        class="lp.registry.model.product.Product">
        <allow
          interface="lp.registry.interfaces.product.IProductPublic"/>
        <require
          permission="launchpad.Edit"
          interface="lp.registry.interfaces.product.IProductEditRestricted"/>
        <require
          permission="launchpad.Edit"
          set_attributes="commercial_subscription description"/>
    </class>

In this example, the EditByOwner adapter's checkAuthenticated method will be
called to determine if the currently authenticated user is authorized to
access whatever is protected by launchpad.Edit on an IProduct.
