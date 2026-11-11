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
locations.  Each item has its own entry in the inventory collection,
even if there are multiple identical items of a type (such as
3D-printers).

Stock items are typically transient, and the stock collection has an
entry for each type of stock item, along with an indication of the
number currently held.  For example, all rolls of paper towel come
under one entry in the collection, rather than being tracked
individually.

Inventory items are each identified by a barcode number, allocated
from the "internal organisational use" block of the EAN-13 barcode
number space (040... to 049...; I have of course chosen 042... as a
well-known number).  They also have names, which must be unique; the
system can find an item from either the number or the name.

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

(Top-level locations, i.e. buildings, are in location 0.  Location
0420000000404 is reserved for things that are not found, i.e. lost.)

Equipment may have a cross-reference to "supplies", giving a stock
type which can be looked up to get a locations list, to look for
supplies.  For example, a wastebin will have a cross-reference to "bin
liners", which you can look up to find where they are kept.

The software
------------

The system includes a web server (and, later, probably a mobile app);
these will be the normal way to access the system as an end user or as
an administrator.  The mobile app interface will be similar to the web
interface, but will integrate the mobile's barcode scanner facility.

The URL paths for most operations start with the barcode or name of
the item, so we can make the barcode labels self-explanatory, with
text like "assets.makespace.org/<n>" above the printed number.  This
gives each item a generated home page.

If the start of the URL path is neither a barcode number nor the name
of an inventory item, the server also searches for matching stock,
then for types.  If it finds a type, the server lists all items of
that type.

Operations which modify the data will require login; read operations
can harmlessly be anonymous.

There may later be some handheld scanning terminals in the space,
forming part of its easy-use facilities (much as the badger does).
These will make it easy to find where to find something or where to
return it to.

Underlying all these is an API server, returning results in JSON.
Most of the logic of the system is in the API server, so that
operations common to all user interfaces can be implemented just once
for all of them.

The JSON API may also be used for any other software that people wish
to add (for example, a server serving pages about training could use
it to find the training pages for a piece of equipment).

Technicalities
--------------

There is also a types collection in the database, which defines a type
hierarchy.  Each item is of one specific type, and each type may
specify a parent type.  When you ask for an attribute of an item, it
is first looked for in the entry for that individual item, then in its
type, then in the parent type of that type, and so on.  This lets us
define attributes for whole classes of items (for example, all laser
cutters are red equipment), but with exceptions as needed.

The underlying database is mongodb, which allows extra fields
("columns") to be added freely; such fields don't occupy space for any
items that don't use them, so feel welcome to add attributes for
specific purposes.

Design choices
--------------

It's easier to get serial-numbered linear barcodes than QR codes, so I
picked barcodes for the system.

Exceptions to rules
-------------------

Classroom-type chairs should probably count as stock, as they neither
need a service schedule nor are good storage locations.

If given a number shorter than 13 digits to identify an item, as many
digits as needed from "0420000000" are prepended to it; this lets us
continue to use our shorter PAT testing labels.
