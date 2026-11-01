#!/usr/bin/env python3

"""API server for managing where we store physical things at makespace.org."""

import csv
import decouple
import io
import pymongo
import re
import urllib
from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

storage_manager = FastAPI()

_database_client = None
_inventory = None
_types = None

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
    return _inventory

def stock():
    """Get the stock collection from the database.

    Each row must define:
    - name
    - quantity
    - location
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

def lookup(name_or_barcode):
    """Find an inventory item by name or by barcode."""
    return (name_or_barcode
            if isinstance(name_or_barcode, dict)
            else ((inventory().find_one({'barcode': int(name_or_barcode)})
                   if isinstance(name_or_barcode, int) or re.match('^[0-9]+$', name_or_barcode)
                   else inventory().find_one({'name': name_or_barcode}))))

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
    print("getting contents of", location)
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
    result = []
    countdown = 8               # in case of looping types
    inv = inventory()
    item = lookup(item)
    # if isinstance(item, int):
    #     item = inv.find_one({'barcode': item})
    while (item := inv.find_one({'barcode': item['location']})):
        result.append(tidy_dictionary(item))
        countdown -= 1
        if countdown == 0:
            break
    return result

def location_string(full_loc, sep=", "):
    """Return a string summarising the given hierarchical location data."""
    typedefs = by_name(types())
    return sep.join(f"{typedefs[surrounder['type']]['preposition']} {surrounder['name']}"
                    for surrounder in full_loc)

@storage_manager.get("/")
async def root():
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/where/{item}")
async def where(item, full=False):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    item = lookup(item)
    location = full_location(item)
    return {'item': tidy_dictionary(item),
            'location': location if full else location_string(location)}

@storage_manager.get("/what/{pattern}")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    return {'matching': pattern,
            'matches': [tidy_dictionary(x)
                        for x in inventory().find({'name': {'$regex': pattern}})]}

def hierarchical_type(item):
    """Return hierarchical type for an item.
    The item may be specified by name or by barcode."""
    typedefs = by_name(types())
    item_dict = lookup(item)
    ty = item_dict['type']
    result = [ty]
    while True:
        ty = typedefs[ty]['parent']
        if ty:
            result.append(ty)
        else:
            break
    return result

def add_types(item):
    """Add the hierarchical types to a dictionary, and return the dictionary."""
    item['types'] = hierarchical_type(item)
    return item

def subtypes(top):
    """Return all the subtypes of a top type, hierarchically."""
    typedefs = by_name(types())
    result = set([top])
    while True:
        how_many = len(result)
        for name, details in typedefs.items():
            if details['parent'] in result:
                result.add(details['name'])
        if len(result) == how_many:
            break
    return result

@storage_manager.get("/type/{type_name}")
async def by_type(type_name):
    """List everything of a given type."""
    return [tidy_dictionary(add_types(x))
            for x in inventory().find({'type': {'$in': list(subtypes(type_name))}})]

@storage_manager.get("/details/{item}")
def details(item):
    """Return the details of an item."""
    data = lookup(item)
    data['types'] = hierarchical_type(item)
    data['location'] = location_string(full_location(item))
    return tidy_dictionary(data)

@storage_manager.get("/attribute/{item}/{attr}")
def attribute(item, attr):
    """Return an attribute of an item.
    This may be defined by the item itself, or in its type hierarchy.
    The item may be specified by name or by barcode."""
    typedefs = by_name(types())
    item_dict = lookup(item)
    if attr in item_dict and item_dict[attr]:
        return {attr: item_dict[attr]}
    item_type = typedefs[item_dict['type']]['name']
    while True:
        if (value := typedefs[item_type][attr]):
            return {attr: value}
        if not (item_type := typedefs[item_type]['parent']):
            break
    return {attr, None}

@storage_manager.get("/list/{location}")
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

@storage_manager.put("/store")
async def store(location: int,
                item: str):
    """Mark that the item is stored in the given location."""
    return {"result": "not stored"} # TODO

@storage_manager.post("/new")
async def new_item(name: str, item_type: str, barcode: int=0):
    """Create a new item.
    An item ID may be given (for example, from a barcode label you have stuck onto something)
    but if it is not given, one will be created for it."""
    database = ensure_database()
    return {'result': "not done"} # TODO

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

def dump_table(collection, left_keys):
    """Dump data from a table into CSV form."""
    data = list(collection.find({}))
    with io.StringIO() as outstream:
        writer = csv.DictWriter(outstream,
                                fieldnames=left_keys + [key
                                                        for key in set().union(*[frozenset(doc.keys())
                                                                                 for doc in data])
                                                        if key not in left_keys and key != '_id'])
        writer.writeheader()
        for row in data:
            writer.writerow({k: v for k, v in row.items() if k != '_id'})
        return StreamingResponse(outstream.getvalue(),
                                 # We could put this in optionally to get browsers to download the result
                                 # but this route is probably mostly for scripted use in which case we
                                 # won't want that:
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
