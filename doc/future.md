Plans and possibilities for the asset system
============================================

History
-------

The database can store when an item was last moved, and when it was
last altered in any other way.  Subject to personal data privacy
concerns, it may be useful to store *who* last moved or altered it.

We could also keep a history of all such changes to each item; this
won't be much data by current standards.

Member items
------------

We could allocate another private-use block of the EAN-13 range (such
as 043) for member-owned items, dividing the remaining ten digits of
it into a member number (probably six digits) and an item number (four
digits).  The database would track these in a separate collection, and
the API would include an endpoint to allocate the next unused number
for a given member.

Then when a member presents their fob to the Badger and asks for a
storage label, the Badger uses the asset API to get a number within
that member's range, and generates a barcoded storage label, while the
asset system registers that item.  The member can then scan the item
and a storage location to register where the item is stored.
Logged-in members on the web interface or the mobile app will be shown
a list of their own stuff, with an indication of where the item is and
when it should be removed by (highlighted if it should be removed soon
or already).  Admins can see this information for all members.

Integration with the door fob system
------------------------------------

If we can be told when a member leaves the building, it will be
possible to highlight on their list of personal items anything that
has been moved since they were last in.