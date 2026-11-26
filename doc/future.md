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
for a given member.  (Members should also be able to allocate numbers
manually, particularly for the case where they run an asset tracking
system such as this one at home or in their organisation.)

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

If we can be told when a member leaves the building, and we have
member items tracking and move timestamping, it will be possible to
highlight on their list of personal items anything that has been moved
since they were last in.

Books
-----

ISBNs fit into the EAN13 range with the prefix 978; the system will
currently treat these as stock items when scanned, as they are not
part of our own range.  They should probably be handled separately, in
a collection of their own.

Image hosting
-------------

There should be room to host a picture of each inventory item on the
server; the item edit form could have an `upload picture` button which
will transfer the picture file and set the `picture` field of the item
to where it has put the picture.
