Storage Manager manual
======================

Introduction
------------

The Makespace Storage Manager tracks the physical assets of Makespace,
principally to help members find things (and to find where to put them
back to after use) but also potentially to help owners look after the
equipment.

The system has two main collections, which are handled differently:

 - inventory

 - stock

The inventory contains persistent items such as equipment and
locations.  Each item has its own entry in the inventory database,
even if there are multiple identical items of a type (such as
3D-printers).

Stock items are transient, and the stock database has an entry for
each type of stock item, along with an indication of the number
currently held.  For example, all rolls of paper towel come under one
entry in the database, rather than being tracked individually.

Inventory items are each identified by a barcode number, allocated
from the "internal organisational use" block of the barcode number
space.  They also have names, which must be unique; the system can
find an item from either the number or the name.

Stock items are identified by type name; any barcodes on them are the
"shop" barcodes (EAN-13 etc).  There may be multiple barcodes for the
same type of item, for example from different suppliers.

Locations
---------

Each inventory item has a location, which is itself an inventory item
which in turn has a location; thus, there is a location hierarchy to
pin down where something is: for example, it could be in a particular
box, which is on a shelf, which is in a set of shelves, which is in a
room, which is in a building; each of those location levels is an
inventory item, and will have a barcode sticker on it.

Stock items may have multiple locations, as all the stock of one type
may not fit in a single location.

(Top-level locations, i.e. buildings, are in location 0.  Location 404
is reserved for things that are not found, i.e. lost.)

Equipment may have a cross-reference to "supplies", giving a stock
type which can be looked up to get a locations list, to look for
supplies.  For example, a wastebin will have a cross-reference to "bin
liners", which you can look up to find where they are kept.

The software
------------

web server, API, terminals

Technicalities
--------------

There is also a types database, which defines a type hierarchy.  When
you ask for an attribute of an item, it is first looked for in the
entry for that individual item, then in its type, then in the parent
type of that type, and so on.  This lets us define attributes for
whole classes of items (for example, all laser cutters are red
equipment), but with exceptions as needed.
