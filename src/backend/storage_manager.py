#!/usr/bin/env python3

"""API server for managing where we store physical things at makespace.org."""

import csv
import io
import re
import urllib

import decouple
import pymongo

from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

storage_manager = FastAPI()

INVENTORY_BARCODE_BASE = "042000000000"
INVENTORY_BARCODE_REGEXP = re.compile("^042[0-9]{10}$")
BARCODE_REGEXP = re.compile("^[0-9]{1,13}$")

storage_manager.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_database_client = None
_types = None
_inventory = None
_stock = None

def _ensure_database():
    """Ensure that we have a connection to the database."""
    global _database_client
    db_name = decouple.config('DATABASE_NAME', 'makespace-storage')
    if not _database_client:
        _database_client = pymongo.MongoClient(
            decouple.config('MONGOURI', "mongodb://localhost:27017/"),
            username=urllib.parse.quote_plus(decouple.config('MONGOUSER', "makespace")),
            password=urllib.parse.quote_plus(decouple.config('MONGOPASSWORD', "")),
            authSource=db_name,
            authMechanism='SCRAM-SHA-1')
        if _database_client is None:
            raise ConnectionError("Could not connect to database")
    return _database_client[db_name]

def types():
    """Get the types collection from the database.

    Each row must define a 'name', and may define:
    - parent (a parent type, except at the top level)
    - preposition (if this is a type of storage location)
    """
    global _types
    if _types is None:
        _types = _ensure_database()['types']
        _types.create_index('name', unique=True) # ignored if it already exists
    return _types

def inventory():
    """Get the inventory collection from the database.

    Each row must define:
    - barcode (the primary identifier in this system)
    - name
    - type
    - location (as a barcode, except for top-level locations)

    Items may also define:
    - width (in metres; this describes the side facing you by default)
    - length (in metres; this describes the side going to/from you by default)
    - height (in metres)
    - level (as a level count above the floor, e.g. in a set of shelves)
    - square (the floor square they are on, such as H3)
    """
    global _inventory
    if _inventory is None:
        _inventory = _ensure_database()['inventory']
        _inventory.create_index('name', unique=True) # ignored if it already exists
        _inventory.create_index('barcode', unique=True) # ignored if it already exists
    return _inventory

def stock():
    """Get the stock collection from the database.

    Each row must define:
    - name
    - quantity
    - locations (as a dictionary of location barcode to quantity in that location)
    """
    global _stock
    if _stock is None:
        _stock = _ensure_database()['stock']
        _stock.create_index('name', unique=True) # ignored if it already exists
    return _stock

def name_to_id(name):
    """Return the barcode of the item with the given name."""
    item = inventory().find_one({'name': name})
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {name} not found")
    return item['barcode']

def id_to_name(barcode):
    """Return the name of an item with the given barcode."""
    return inventory().find_one({'barcode': barcode})['name']

def normalise_barcode(barcode):
    """Return a barcode as a string, based on the given input which
    may be a string or an int.

    If it is a number with fewer than 12 digits, it is suffixed with
    as many digits as needed from our inventory barcode numbering
    base.  It may also be given as a dictionary, from which the
    'barcode' entry is used, so this is as far as possible a universal
    way of getting a barcode matching a description.

    """
    barcode_string = str(dict['barcode']
                         if isinstance(barcode, dict)
                         else barcode)
    return (INVENTORY_BARCODE_BASE[:13-len(barcode_string)] + barcode_string
            if len(barcode_string) < 12 # allow for UPC-12, but our own are EAN-13
            else barcode_string)

def lookup(name_or_barcode):
    """Find an item by name or by barcode.

    The argument may be a name, or a barcode given as a string or a
    number.

    The inventory is searched first, then the stock, then the type system.

    Returns a dictionary representing the entire database entry for
    the item, with the key 'kind' set to indicate what kind of item
    was found: 'inventory', 'stock', or 'type'; or if a dictionary was
    passed in as the argument and did not indicate its kind, it is
    marked as being of an 'unknown' kind.
    """

    def mark_kind(item, kind):
        item['kind'] = kind
        return item

    if isinstance(name_or_barcode, dict):
        if 'kind' not in name_or_barcode:
            name_or_barcode['kind'] = 'unknown'
        return name_or_barcode
    if is_barcode(name_or_barcode):
        barcode = normalise_barcode(name_or_barcode)
        return mark_kind((inventory if is_inventory(barcode) else stock)()
                         .find_one({'barcode': int(barcode)}),
                         'inventory')
    if (item := inventory().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'inventory')
    if (item := stock().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'stock')
    if (item := types().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'type')
    return None

def direct_contents(location_barcode):
    """Return a list of things that have the given barcode as their location."""
    return list(tidy_dictionary(d) for d in inventory().find({'location': location_barcode}))

def add_contents(entry):
    """Add to this entry a 'contents' list of the things that list it as their location.
    Recurse down."""
    things = direct_contents(entry['barcode'])
    if things:
        for thing in things:
            add_contents(thing)
        entry['contents'] = things

def contents(location, recursive=False):
    """Return the contents of the given location.
    The location may be given by barcode or name.
    With the recursive flag, add a 'contents' entry for each item."""
    top_level = direct_contents(lookup(location)['barcode'])
    if recursive:
        for entry in top_level:
            add_contents(entry)
    return top_level

def set_location(location_id, barcode):
    """Set the location of an item."""
    inventory().update({'barcode': barcode}, {'location': location_id}, upsert=True)

def by_name(collection):
    """Return a dictionary of a collection's contents, with the names as the keys."""
    return {entry['name']: entry for entry in collection.find({})}

def tidy_dictionary(dictionary):
    """Return a copy of a dictionary with empty strings removed.
    ObjectIds are also removed."""
    return {k: v for k, v in dictionary.items()
            if v != "" and not isinstance(v, ObjectId)}

def full_location(item):
    """Return the full hierarchical location data for an item.
    The item may be given as a barcode or a dictionary."""
    typedefs = by_name(types())
    result = []
    countdown = 8               # in case of looping types
    inv = inventory()
    item = lookup(item)
    while (item := inv.find_one({'barcode': item['location']})):
        item['preposition'] = typedefs[item['type']]['preposition']
        result.append(tidy_dictionary(item))
        countdown -= 1
        if countdown == 0:
            break
    return result

def location_string(full_loc, sep=", "):
    """Return a string summarising the given hierarchical location data."""
    return sep.join(
        f"{surrounder['preposition']} {surrounder['name']}"
        for surrounder in full_loc)

@storage_manager.get("/")
async def root():
    """Return the root document of the API."""
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/sites")
async def sites():
    """Return a list of top-level site names."""
    return {'sites': [site['name'] for site in inventory().find({'location': 0})]}

@storage_manager.get("/top-level-types")
def top_level_types():
    """Return the top-level types.
    This is the types that have no parent type."""
    return {'types': [t['name'] for t in types().find({'parent': ""})]}

def links_for_item(base_url: str, item: dict):
    """Return the API links for an item."""
    links = {
        label: f"{base_url}/{label}" for label in [
            "details",
            "where",
            # "type",
        ]
    }
    if not item.get('fixed', False):
        links['move'] = f"{base_url}/move/" + "{location}"
    if False:                   # don't allow this while the project is at the demo stage
        links['delete'] = f"{base_url}/delete"
    if direct_contents(item['barcode']):
        links['contains'] = f"{base_url}/contains"
    return links

@storage_manager.get("/{item}")
async def item_home(item, request: Request):
    item_dict = lookup(item)
    return (({'name': item_dict['name'],
              'kind': item_dict['kind']}
             if item_dict['kind'] == 'type'
             else {'name': item_dict['name'],
                   'type': item_dict['type'],
                   'kind': item_dict['kind'],
                   'links': links_for_item(request.url, item_dict)})
            if item_dict
            else {'links': {'new': f"request.url{item}/new"}})

@storage_manager.get("/{item}/where")
async def where(item, full=False):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    item = lookup(item)
    location = full_location(item)
    return {'item': tidy_dictionary(item),
            'nest': location,
            'location': location_string(location)}

@storage_manager.get("/{pattern}/what")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    return {'matching': pattern,
            'matches': [tidy_dictionary(x)
                        for x in inventory().find({'name': {'$regex': pattern}})]}

def hierarchical_type(item):
    """Return hierarchical type for an item.
    The item may be specified by name or by barcode."""
    item_dict = lookup(item)
    if item_dict is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return parent_type_list(item_dict['type'])

def parent_type_list(ty):
    """Return the parent types of a type."""
    typedefs = by_name(types())
    result = [ty]
    while True:
        ty = typedefs.get(ty, {}).get('parent', None)
        if ty:
            result.append(ty)
        else:
            break
    return result

def add_types(item):
    """Add the hierarchical types to a dictionary, and return the dictionary."""
    item['types'] = hierarchical_type(item)
    return item

def subtypes_set(top):
    """Return the set of all the subtypes of a top type, hierarchically."""
    typedefs = by_name(types())
    result = set([top])
    while True:
        how_many = len(result)
        for name, type_details in typedefs.items():
            if type_details['parent'] in result:
                result.add(type_details['name'])
        if len(result) == how_many:
            break
    return result

@storage_manager.get("/{type_name}/subtypes")
async def subtypes(type_name):
    """Return the subtypes of a given type."""
    return list(subtypes_set(type_name))

@storage_manager.get("/{type_name}/parent_types")
async def parent_types(type_name):
    """Return the parent types of a given type."""
    return parent_type_list(type_name)

@storage_manager.get("/{type_name}/list_type")
async def by_type(type_name):
    """List everything of a given type."""
    return [tidy_dictionary(add_types(x))
            for x in inventory().find({'type': {'$in': list(subtypes_set(type_name))}})]

@storage_manager.get("/{item}/details")
def details(item):
    """Return the details of an item."""
    loc = full_location(item)
    return {
        'types': hierarchical_type(item),
        'nest': loc,
        'location': location_string(loc),
        'details': tidy_dictionary(lookup(item)),
    }

@storage_manager.get("/{item}/attribute/{attr}")
def attribute(item, attr, local_only=None):
    """Return an attribute of an item.
    This may be defined by the item itself, or in its type hierarchy.
    The item may be specified by name or by barcode."""
    typedefs = by_name(types())
    item_dict = lookup(item)
    if attr in item_dict and item_dict[attr]:
        return {attr: item_dict[attr]}
    if local_only:
        return {attr: None}
    if item_dict['type'] in typedefs:
        item_type = typedefs[item_dict['type']]['name']
        while True:
            if item_type not in typedefs:
                return {attr: None}
            if (value := typedefs[item_type][attr]):
                return {attr: value}
            if not (item_type := typedefs[item_type]['parent']):
                break
    return {attr: None}

@storage_manager.get("/{location}/contents")
async def list_contents(location, recursive:bool = False):
    """List everything stored in the given location."""
    return {'location': location,
            'contents': [tidy_dictionary(x) for x in contents(location,
                                                              recursive)]}

@storage_manager.get("/map")
async def map_contents(location: int=0, items=None):
    """Return data suitable for making a visual representation
    of where things are within a location.
    A collection of items to emphasize may be given."""
    # TODO: get the items within the location, and make their coordinates relative to the location
    # TODO: set the type of the resulting data
    return data         # TODO

def is_barcode(code):
    """Return whether a string looks like a barcode (rather than name).
    If an int is given, it is assumed to be a barcode."""
    return (isinstance(code, int)
            or BARCODE_REGEXP.match(code))

def is_inventory(barcode):
    """Return whether a barcode is an inventory barcode."""
    return INVENTORY_BARCODE_REGEXP.match(str(barcode))

def is_stock(barcode):
    """Return whether a barcode is a stock barcode."""
    return not is_inventory(barcode)

@storage_manager.post("/{item}/move/{location}")
async def store(item: str,
                location: int,
                quantity: int):
    """Mark that the item is stored in the given location."""
    barcode = lookup(item)['barcode']
    if is_inventory(barcode):
        inv = inventory()
        if inv.find_one({'barcode': location}):
            inv.update_one({'barcode': barcode},
                           {'$set': {'location': location}},
                           upsert=True)
            return {'barcode': barcode, 'location': location}
        raise HTTPException(status_code=404,
                            detail=f"Location {location} not found when storing an item")
    else:
        pass                    # TODO store stock separately, using quantity

VIRTUAL_BARCODE_ISSUE_BASE = 1000000

@storage_manager.post("/{name}/new/{item_type}/{location}/{barcode}")
async def new_item(name: str, item_type: str, location: int, barcode: int, request: Request):
    """Create a new item.

    An item ID may be given (for example, from a barcode label you have stuck onto something)
    but if it is not given, one will be created for it.

    Further fields may be given in the request body."""
    inv = inventory()
    if barcode:
        if inv.find_one({'barcode': barcode}):
            raise HTTPException(status_code=500, detail=f'Barcode {barcode} already in use')
    else:
        barcode = 1 + max(VIRTUAL_BARCODE_ISSUE_BASE,
                          inv.find({}).sort({'barcode': -1}).limit(1).next()['barcode'])
    inv.insert_one({'barcode': barcode,
                    'name': name,
                    'type': item_type,
                    'location': location}
                   # further fields may be given in the request body
                   | await request.json())
    return {'result': "not done"} # TODO

@storage_manager.post("/{item}/delete")
async def delete_item(item: str):
    """Delete an item, specified by name or barcode."""
    deledendum = lookup(item)
    if deledendum is None:
        raise HTTPException(status_code=404, detail=f"Item {item} not found for deletion")
    barcode = deledendum['barcode']
    inventory().delete_one({'barcode': barcode})
    return {'deleted': barcode}

def convert_string(raw):
    """Convert a string to int or float if possible."""
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw

def convert_dict_entries(row):
    """Convert strings in the data to int or float if possible."""
    return {k: convert_string(v) for k, v in row.items()}

def load_table(collection, text):
    """Load data into a database collection from a CSV POST body."""
    count = 0
    try:
        for row in csv.DictReader(io.StringIO(text)):
            collection.update_one({'name': row['name']},
                                  {'$set': convert_dict_entries(row)},
                                  upsert=True)
            count += 1
    except Exception as e:
        print("problem while uploading a data table:", e)
        raise HTTPException(status_code=500, detail='Something went wrong')
    return {"result": f"inserted or updated {count} entries"}

def bring_to_front(left_keys, all_keys):
    """Return a list of keys with specific ones brought to the front."""
    return (left_keys + [key
                         for key in all_keys
                         if key not in left_keys and key != '_id'])

def all_keys_of_all_documents(data):
    """Return all the keys of all the documents."""
    return set().union(*[frozenset(doc.keys())
                         for doc in data])

def dump_table(collection, left_keys):
    """Dump data from a table into CSV form."""
    data = list(collection.find({}))
    with io.StringIO() as outstream:
        writer = csv.DictWriter(
            outstream,
            fieldnames=bring_to_front(left_keys,
                                      all_keys_of_all_documents(data)))
        writer.writeheader()
        for row in data:
            writer.writerow({k: v for k, v in row.items() if k != '_id'})
        return StreamingResponse(outstream.getvalue(),
                                 # We could put this in optionally to get browsers to download the result
                                 # but this route is probably mostly for scripted use in which case we
                                 # won't want that as we'd prefer to get the data on stdout:
                                 # headers={"Content-Disposition": 'attachment; filename="export.csv"'},
                                 media_type="text/csv")

@storage_manager.post("/load-types")
async def load_types(request: Request):
    """Load data into the database types from a CSV POST body."""
    return load_table(types(),
                      (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-types")
async def dump_types():
    """Return the database types as CSV text."""
    return dump_table(types(), left_keys=['name', 'parent'])

@storage_manager.post("/load-inventory")
async def load_inventory(request: Request):
    """Load data into the database inventory from a CSV POST body."""
    return load_table(inventory(), (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-inventory")
async def dump_inventory():
    """Return the database inventory as CSV text."""
    return dump_table(inventory(), left_keys=['barcode', 'name', 'type', 'location', 'square'])

@storage_manager.post("/load-stock")
async def load_stock(request: Request):
    """Load data into the database stock from a CSV POST body."""
    return load_table(stock(), (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-stock")
async def dump_stock():
    """Return the database stock as CSV text."""
    return dump_table(stock(), left_keys=['name', 'quantity', 'location'])
