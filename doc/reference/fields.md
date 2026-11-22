# Makespace storage manager fields help

## barcode

The barcode of the item.  This is stored as a number, which results in
the leading zero being lost.  If it is shorter than 13 digits, it is
filled in at the left with as much as needed of our barcode prefix,
which is `042000000000`

Barcodes in the system must be unique.

## name

The name of the item.  This must be unique.

## type

The type of the item.  This should be the same as an entry in the `type` column of the types collection.

## location

The immediately surrounding location of the item.

Locations are also items, which have locations, so they are nested,
and the software uses this to make a full description: for example,
something could be in a box on a shelf in a stack of shelves in a room
in a building.

The location field of an item should be the barcode of the location.

Items with a location barcoded as `0` are top-level locations, that
is, buildings.

## fixed

A non-empty `fixed` field indicates that no `Move` option should be
offered for the item.

## preposition

The preposition to use to say that this is the container for
something.  For example, for a box or a room, it will be `in` but for
a shelf it will be `on`.

## Manufacturer

The name of the manufacturer.

## Manufacturer_URL

The URL of the home page of the manufacturer.

## Manufacturer_page

The title for the manufacturer's page for this equipment.

## Manufacturer_page_URL

The URL of the manufacturer's page for this equipment.

## Supplier

The name of the company we bought this item from.

## Supplier_URL

The supplier's home page URL (for their company as a whole, not for
this specific piece of equipment).

## Supplier_page

The title for the page for this equipment at the company we bought it from.

## Supplier_page_URL

The supplier's page URL for this type of equipment.

## Date_acquired

The date we acquired this equipment, as an
[ISOdate](https://en.wikipedia.org/wiki/ISO_8601#Calendar_dates).

## Date_disposed

The date we got rid of this equipment, as an
[ISOdate](https://en.wikipedia.org/wiki/ISO_8601#Calendar_dates).
Later versions of the software may option hide from the listings items
which have been disposed at a past date.

## PAT tested

The date this equipment was last PAT tested, as an
[ISOdate](https://en.wikipedia.org/wiki/ISO_8601#Calendar_dates).

## Picture

The URL of an image to display inline.

## Training_page

The URL of a page in our training web site.

## Owners_email

The email of the owners (without the `mailto:`).

## Grid_location

The metre square coordinates as letters (across or X coordinate) and
numbers (away or Y coordinate).

As is common in graphs and charts, the coordinate origin (A0) is at
the near left corner of the building as seen looking in from the main
entrance.  Across coordinates beyond `Z` are written as `AA`, `AB`,
etc, as in spreadsheets.

A vertical coordinate may follow, to give which floor the item is on.
To mark this as separate from the Y coordinate (which is digits) this
is a letter; this also avoids dispute about floor numbering.
Conveniently, the initial letters of these floor names are in
alphabetical order:

 - Basement
 - Ground
 - Lower
 - Middle
 - Upper

This may be followed by a level number, for example to indicate which
of a stack of shelves is referred to.  For this, the bottom shelf is
numbered `1`, leaving `0` available to indicate that something is
stored on the floor under the shelves.

## Supplies

Semicolon-separated list of stock type names of supplies.  Whitespace
around the semicolons is stripped.

The barcodes of stock items are mapped onto the stock type names by a
separate collection in the database, as there may be equivalent stock
with different barcodes from different suppliers.
