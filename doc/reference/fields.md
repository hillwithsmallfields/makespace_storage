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

## Manufacturer

The name of the manufacturer

## Manufacturer_URL

This should be the home page of the manufacturer.

## Manufacturer_page

The title for the manufacturer's page for this equipment

## Manufacturer_page_URL

This should be the manufacturer's page for this equipment.

## Supplier

The name of the company we bought this item from.

## Supplier_URL

The supplier's home page.

## Supplier_page

The title for the page for this equipment at the company we bought it from.

## Supplier_page_URL

The supplier's page for this type of equipment.

## Date_acquired

The date we acquired this equipment, as an ISOdate.

## Date_disposed

The date we got rid of this equipment, as an ISOdate.  Later versions
of the software may option hide from the listinga items which have
been disposed at a past date.

## PAT tested

The date this equipment was last PAT tested.

## Picture

The URL of an image to display inline.

## Training_page

The URL of a page in our training web site.

## Owners_email

The email of the owners (without 'mailto:')

## Grid location

The metre square coordinates as letters (across) and numbers (away).

## Supplies

Semicolon-separated list of stock type names of supplies.

