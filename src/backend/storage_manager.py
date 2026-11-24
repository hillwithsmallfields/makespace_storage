#!/usr/bin/env python3

"""API server for managing where we store physical things at makespace.org."""

import csv
import io
import json
import re
import urllib

from typing import Annotated, Any

import decouple
import pymongo

from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException, Request, Form, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

storage_manager = FastAPI()

INVENTORY_BARCODE_BASE = "042000000000"
INVENTORY_BARCODE_REGEXP = re.compile("^0?42[0-9]{10}$")
BARCODE_REGEXP = re.compile("^[0-9]{1,13}$")
DUMMY_BARCODE_BASE = "099000000000"

storage_manager.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INVENTORY_FIELDS = [
    ["name", "The name of the item"],
    ["location", "The immediately surrounding location of the item.", 'location'],
    ["type", "The type of the item", 'type'],
    ["Manufacturer", "The name of the manufacturer"],
    ["Manufacturer_URL", "This should be the home page of the manufacturer."],
    ["Manufacturer_page", "The title for the manufacturer's page for this equipment"],
    ["Manufacturer_page_URL", "This should be the manufacturer's page for this equipment."],
    ["Supplier", "The name of the company we bought this item from."],
    ["Supplier_URL", "The supplier's home page."],
    ["Supplier_page", "The title for the page for this equipment at the company we bought it from."],
    ["Supplier_page_URL", "The supplier's page for this type of equipment."],
    ["Date_acquired", "The date we acquired this equipment, as an ISOdate."],
    ["Date_disposed", "The date we got rid of this equipment, as an ISOdate.  We may exclude from listing items disposed of in the past."],
    ["PAT_tested", "The date this equipment was last PAT tested."],
    ["Picture", "The URL of an image to display inline."],
    ["Training_page", "The URL of a page in our training web site."],
    ["Owners_email", "The email of the owners (without 'mailto:')"],
    ["Grid_location", "The metre square coordinates as letters (across) and numbers (away)."],
    ["Supplies", "Semicolon-separated list of stock type names of supplies.", 'supplies'],
    ["barcode", "The barcode of the item."],
]

STOCK_FIELDS = [
    "locations",
    "Supplier", "Supplier_URL",
    "Minimum_stock",
    "Order_size",
]

_database_client = None
_types = None
_stock_types = None
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

def types_data():
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

def stock_types_data():
    """Get the stock types collection from the database.

    Each row must define a 'barcode' and a 'name'.
    It may also define a 'description'."""
    global _stock_types
    if _stock_types is None:
        _stock_types = _ensure_database()['stock_types']
        _stock_types.create_index('name', unique=True) # ignored if it already exists
    return _stock_types

def inventory_data():
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

def stock_data():
    """Get the stock collection from the database.

    Each row must define:
    - type (which should match a type in the stock_types_data collection)
    - location (as a barcode)
    - quantity
    """
    global _stock
    if _stock is None:
        _stock = _ensure_database()['stock']
        _stock.create_index('name', unique=True) # ignored if it already exists
    return _stock

def name_to_id(name):
    """Return the barcode of the item with the given name."""
    item = inventory_data().find_one({'name': name})
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {name} not found")
    return item['barcode']

def id_to_name(barcode):
    """Return the name of an item with the given barcode."""
    return inventory_data().find_one({'barcode': barcode})['name']

@storage_manager.get("/name/{barcode}")
def name(barcode):
    """Look up a barcode (or name) and return a name."""
    found = lookup(barcode)
    return {'barcode': found['barcode'], 'name': found['name']}

def next_dummy_barcode():
    """Return the next dummy barcode."""
    return int(inventory_data().find({}).sort({'barcode' : -1}).next()['barcode']) + 1

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
        is_inv = is_inventory(barcode)
        found = ((inventory_data if is_inv else stock_data)()
                 .find_one({'barcode': int(barcode)}))
        if found:
            return mark_kind(found, 'inventory' if is_inv else 'stock')
        return {'kind': 'new_inventory' if is_inv else 'new_stock',
                'barcode': int(barcode)}
    if (item := inventory_data().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'inventory')
    if (item := stock_data().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'stock')
    if (item := types_data().find_one({'name': name_or_barcode})):
        return mark_kind(item, 'type')
    return None

def direct_contents(location_barcode):
    """Return a list of things that have the given barcode as their location."""
    return list(tidy_dictionary(d)
                for d in inventory_data().find({'location': location_barcode}))

def inventory_contents(location, recursive=False):
    """Return the contents of the given location.
    The location may be given by barcode or name.
    With the recursive flag, add a 'contents' entry for each item."""

    def add_contents(entry):
        """Add to this entry a 'contents' list of the things that list it as their location.
        Recurse down."""
        things = direct_contents(entry['barcode'])
        if things:
            for thing in things:
                add_contents(thing)
            entry['contents'] = things

    top_level = direct_contents(lookup(location)['barcode'])
    if recursive:
        for entry in top_level:
            add_contents(entry)
    return top_level

def set_location(location_id, barcode):
    """Set the location of an item."""
    inventory_data().update({'barcode': barcode},
                            # force this one to its numeric form
                            {'location': int(lookup(location_id)['barcode'])},
                            upsert=True)

@storage_manager.get("/locations_for/{typename}")
def locations_for(typename):
    """Return the names of locations that a given type of item may be stored in.
    Uses the 'fits' column of the database, which is a semicolon-separated list of location types."""
    fitting_location_types = [loctype.strip()
                              for loctype in (type_attribute(typename, 'fits', default="").split(';')) or []]
    return {'location_types': fitting_location_types,
            'locations': [item['name']
                          for item in inventory_data().find({})
                          if item['type'] in fitting_location_types]}

def by_name(collection):
    """Return a dictionary of a collection's contents, with the names as the keys."""
    return {entry['name']: entry for entry in collection.find({})}

def tidy_dictionary(dictionary):
    """Return a copy of a dictionary with empty strings removed.
    ObjectIds are also removed."""
    return {k: v for k, v in dictionary.items()
            if v != "" and not isinstance(v, ObjectId)}

def fill_out_location(location_name):
    """Fill out an immediate location with its surrounding locations."""
    if location_name in (0, "0", "", None):
        return []
    typedefs = by_name(types_data())
    result = []
    countdown = 8               # in case of looping types
    inv = inventory_data()
    while (item := inv.find_one({'barcode': int(location_name)})):
        item['preposition'] = typedefs[item['type']]['preposition']
        location_name = item['location']
        result.append(tidy_dictionary(item))
        countdown -= 1
        if countdown == 0:
            break
    return result

def full_location(item):
    """Return the full hierarchical location data for an item.
    The item may be given as a barcode or a dictionary."""
    item = lookup(item)
    match item['kind']:
        case 'inventory':
            return fill_out_location(item['location'])
        case 'stock':
            return [fill_out_location(partial_stock)
                    for partial_stock in item['locations']]
        case _:
            return []

def location_string(full_loc, sep=", "):
    """Return a string summarising the given hierarchical location data."""
    return ((";".join([location_string(sub) for sub in full_loc])
             if isinstance(full_loc[0], list)
             else sep.join(f"{surrounder['preposition']} {surrounder['name']}"
                           for surrounder in full_loc))
            if full_loc
            else "")

def convert_string(raw):
    """Convert a string to int or float if possible;
    or JSON if it looks likely."""
    if isinstance(raw, str) and raw.startswith('{') and raw.endswith('}'):
        try:
            jtext = raw.replace("'", '"')
            return json.loads(jtext)
        except Exception as jsonerror:
            return raw
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw

def convert_dict_entries(row):
    """Convert strings in the data to int or float if possible;
    or JSON if it looks likely."""
    return {k: convert_string(v) for k, v in row.items()}

def load_table(collection, text, key='name'):
    """Load data into a database collection from a CSV POST body."""
    count = 0
    try:
        for row in csv.DictReader(io.StringIO(text)):
            res = collection.update_one({key: row[key]},
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

# All the paths which begin with commands must come before the path "/":

@storage_manager.post("/load-types")
async def load_types(request: Request):
    """Load data into the database types from a CSV POST body."""
    return load_table(types_data(),
                      (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-types")
async def dump_types_data():
    """Return the database types as CSV text."""
    return dump_table(types_data(), left_keys=['name', 'parent'])

@storage_manager.post("/load-stock-types")
async def load_stock_types(request: Request):
    """Load data into the stock database types from a CSV POST body."""
    return load_table(stock_types_data(),
                      (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-stock-types")
async def dump_stock_types_data():
    """Return the stock database types as CSV text."""
    return dump_table(stock_types_data(), left_keys=['barcode', 'name'])

@storage_manager.post("/load-inventory")
async def load_inventory(request: Request):
    """Load data into the database inventory from a CSV POST body."""
    return load_table(inventory_data(), (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-inventory")
async def dump_inventory():
    """Return the database inventory as CSV text."""
    return dump_table(inventory_data(), left_keys=['barcode', 'name', 'type', 'location', 'square'])

@storage_manager.post("/load-stock")
async def load_stock(request: Request):
    """Load data into the database stock from a CSV POST body."""
    return load_table(stock_data(), (await request.body()).decode("utf-8"))

@storage_manager.get("/dump-stock")
async def dump_stock():
    """Return the database stock as CSV text."""
    return dump_table(stock_data(), left_keys=['name', 'quantity', 'location'])

@storage_manager.get("/search")
def search(pattern):
    """Look for matches for a pattern."""
    return {'inventory': [tidy_dictionary(m) for m in inventory_data().find({'name': {'$regex': pattern}})],
            'stock': [tidy_dictionary(m) for m in stock_data().find({'name': {'$regex': pattern}})],
            'types': [tidy_dictionary(m) for m in types_data().find({'name': {'$regex': pattern}})],
            'stock_types': [tidy_dictionary(m) for m in stock_types_data().find({'name': {'$regex': pattern}})]}

@storage_manager.get("/")
async def root():
    """Return the root document of the API."""
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/sites")
async def sites():
    """Return a list of top-level site names."""
    return {'sites': [site['name'] for site in inventory_data().find({'location': 0})]}

@storage_manager.get("/inventory-types")
def inventory_types():
    """Return all the inventory types."""
    return {'types': [t['name'] for t in types_data().find({})]}

@storage_manager.get("/stock-types")
def stock_types():
    """Return all the stock types."""
    return {'types': sorted(set([t['name'] for t in stock_types_data().find({})]
                                + [t['name'] for t in stock_data().find({})]))}

@storage_manager.get("/top-level-types")
def top_level_types():
    """Return the top-level types.
    This is the types that have no parent type."""
    return {'types': [t['name'] for t in types_data().find({'parent': ""})]}

@storage_manager.get("/suggested_fields")
def suggested_fields():
    return {'inventory': INVENTORY_FIELDS,
            'stock': STOCK_FIELDS}

VIRTUAL_BARCODE_ISSUE_BASE = 1000000

@storage_manager.post("/new_inventory")
def new_inventory(request: Request):
    item_name = request.query_params['item_name']
    fields = dict(request.query_params.items())
    if not fields.get('barcode'):
        fields['barcode'] = next_dummy_barcode()
    print("new inventory with fields", fields)
    r = inventory_data().update_one({'name': item_name}, # TODO: perhaps? identify it by barcode rather than name
                                    {'$set': convert_dict_entries(fields)},
                                    upsert=True)
    return {'created': "inventory item",
            'result': str(r),
            'item_name': item_name,
            'item_type': request.query_params['item_type']}

@storage_manager.post("/new_stock")
def new_stock(request: Request):
    item_name = request.query_params['item_name']
    item_type = request.query_params['item_type']
    print("in new_stock_item post with name", item_name, "and item type", item_type)
    # TODO: add the item to the database
    return {'created': "inventory item",
            'item_name': item_name,
            'item_type': item_type}

@storage_manager.post("/new_type")
def new_type(request: Request):
    for k, v in request.query_params.items():
        print("  got param", k, v)
    type_name = request.query_params['type_name']
    print("in new_type_item post with name", item_name)
    return {'created': "type",
            'type': type_name}

@storage_manager.post("/link_stock_type")
def link_stock_type(request: Request):
    type_name = request.query_params['type_name']
    if type_name == "New stock type":
        type_name = request.query_params['new_stock_type']
    barcode = request.query_params['barcode']
    r = stock_types_data().update_one({'barcode': barcode},
                                      {'$set': {'type': type_name}})
    return {'linked': "inventory item",
            'result': str(r),
            'barcode': barcode,
            'type': type_name}

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
    if 'barcode' in item and direct_contents(item['barcode']):
        links['contains'] = f"{base_url}/contains"
    return links

@storage_manager.get("/item/{item}")
async def item_home(item, request: Request):
    """Return a 'home page' for the item.
    If the item does not exist, return a result to help create it."""
    print("in /item for", item)
    item_dict = lookup(item)
    return ({'links': {'new': f"{request.url}/new/unknown"},
             'kind': 'unknown'}
            if item_dict is None
            else ({'name': item_dict['name'],
                   'kind': item_dict['kind']}
                  if item_dict['kind'] == 'type'
                  else ({'name': item_dict['name'],
                         'type': item_dict.get('type', 'unknown'),
                         'kind': item_dict['kind'],
                         'links': links_for_item(request.url, item_dict)}
                        if not item_dict['kind'].startswith('new_')
                        else {'kind': item_dict['kind'],
                              'barcode': item_dict['barcode']})))

@storage_manager.get("/supplies/{item}")
def supplies(item):
    """Return the supplies for an item."""
    types = stock_types_data()
    return {st: {defn['barcode'] for defn in types.find({'name': st})}
            for st in [s.strip()
                       for s in lookup(item).get('supplies', "").split(';')
                       if s]}

@storage_manager.get("/where/{item}")
async def where(item, full=False):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    item = lookup(item)
    match item['kind']:
        case 'inventory':
            location = full_location(item)
            return {'item': tidy_dictionary(item),
                    'nest': location,
                    'location': location_string(location)}
        case 'stock':
            locations = item['locations']
            return {'name': name,
                    'locations': locations}
        case _:
            return {}

def stock_contents_at_location(location):
    """Return what is stocked at this location."""
    return [contents for contents in stock_data().find({'location': lookup(location)['barcode']})]

def locations_of_stock(stock):
    """Return the locations of a stock type."""
    return [loc for loc in stock_data().find({'name': stock})]

@storage_manager.get("/stocked/{location}")
async def stocked(location):
    return stock_contents_at_location(location)

@storage_manager.get("/stock/{stocktype}")
async def stock_locations(stocktype):
    return locations_of_stock(stocktype)

@storage_manager.get("/levels/{item}")
def stock_levels(item):
    """Return the stock levels of an item."""
    for s in stock_data().find({'name': item}):
        print("found", s)
    return {s['location']: s['quantity'] for s in stock_data().find({'name': item})}

@storage_manager.post("/update_stock")
def update_stock(request: Request):
    action = request.query_params['action'][0],
    delta = int(request.query_params['delta']) * (-1 if action == '-' else 1)
    stock_item = request.query_params['stock_item']
    location = str(lookup(request.query_params['location'])['barcode'])
    existing = request.query_params['existing']
    referring_page = request.query_params['referring_page']
    print("in update_stock with action", action, "delta:", delta, "stock_item:", stock_item, "location:", location, "existing:", existing, "referring_page:", referring_page)
    # TODO: mongo stuff for this
    data = stock_data()
    # if action == '=':
    #     data.update_one({'name': stock_item,
    #                      f"locations.{location}"}, {'$set': delta})
    # else:
    #     data.update_one({'name': stock_item,
    #                      f"locations.{location}"}, {'$inc': delta})
    return {'placeholder': f"updated {stock_item} locations.{location}"}

@storage_manager.get("/what/{pattern}")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    return {'matching': pattern,
            'matches': [tidy_dictionary(x)
                        for x in inventory_data().find({'name': {'$regex': pattern}})]}

def hierarchical_type(item):
    """Return hierarchical type for an item.
    The item may be specified by name or by barcode."""
    item_dict = lookup(item)
    if item_dict is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return parent_type_list(item_dict['type'])

def parent_type_list(ty):
    """Return the parent types of a type."""
    typedefs = by_name(types_data())
    result = [ty]
    while True:
        ty = typedefs.get(ty, {}).get('parent', None)
        if ty:
            result.append(ty)
        else:
            break
    return result

def is_instance(item, typename):
    return typename in [ty['name'] for ty in parent_type_list(typename)]

def add_types(item):
    """Add the hierarchical types to a dictionary, and return the dictionary."""
    item['types'] = hierarchical_type(item)
    return item

def subtypes_set(top):
    """Return the set of all the subtypes of a top type, hierarchically."""
    typedefs = by_name(types_data())
    result = set([top])
    while True:
        how_many = len(result)
        for name, type_details in typedefs.items():
            if type_details['parent'] in result:
                result.add(type_details['name'])
        if len(result) == how_many:
            break
    return result

@storage_manager.get("/subtypes/{type_name}")
async def subtypes(type_name):
    """Return the subtypes of a given type."""
    return list(subtypes_set(type_name))

@storage_manager.get("/parent_types/{type_name}")
async def parent_types(type_name):
    """Return the parent types of a given type."""
    return parent_type_list(type_name)

@storage_manager.get("/list_type/{type_name}")
async def by_type(type_name):
    """List everything of a given type."""
    return [tidy_dictionary(add_types(x))
            for x in inventory_data().find({'type': {'$in': list(subtypes_set(type_name))}})]

@storage_manager.get("/details/{item}")
def details(item):
    """Return the details of an item."""
    loc = full_location(item)
    return {'types': hierarchical_type(item),
            'nest': loc,
            'location': location_string(loc),
            'details': tidy_dictionary(lookup(item))}

def type_attribute(typename, attr, typedefs=None, default=None):
    """Return an attribute of a type."""
    if typedefs is None:
        typedefs = by_name(types_data())
    while True:
        if typename not in typedefs:
            return default
        if (value := typedefs[typename].get(attr)):
            return value
        if not (typename := typedefs[typename]['parent']):
            return default

def item_attribute(item, attr, local_only=None):
    """Return an attribute of an item.
    This may be defined by the item itself, or in its type hierarchy.
    The item may be specified by name or by barcode."""
    item_dict = lookup(item)
    if attr in item_dict and item_dict[attr]:
        return item_dict[attr]
    if local_only:
        return None
    typedefs = by_name(types_data())
    key = 'name' if item_dict['kind'] == 'type' else 'type'
    if item_dict[key] in typedefs:
        return type_attribute(item_dict[key], attr, typedefs=typedefs)
    return None

@storage_manager.get("/attribute/{item}/{attr}")
def attribute(item, attr):
    """FastAPI wrapper for `item_attribute`."""
    return {attr: item_attribute(item, attr)}

@storage_manager.get("/attributes/{item}/{attrs}")
def attributes(item, attrs):
    """FastAPI wrapper for `item_attributes`."""
    return {attr: value
            for attr in attrs.split(';')
            if ((value := item_attribute(item, attr)) is not None)}

@storage_manager.post("/update_inventory_item")
async def update_item(payload: dict[str, Any] = Body(...)):
    item_name = payload.pop('item_name')
    inventory_data().update_one({'name': item_name}, # TODO: identify it by barcode rather than name
                                {'$set': dict(payload.items())},
                                upsert=True)
    return {'updated': item_name}

@storage_manager.get("/contents/{location}")
async def list_contents(location, recursive:bool = False):
    """List everything stored in the given location."""
    return {'location': location,
            'inventory': [tidy_dictionary(x)
                          for x in inventory_contents(location,
                                                      recursive)],
            'stock': [tidy_dictionary(x)
                      for x in stock_contents_at_location(location)]}

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

@storage_manager.post("/move")
async def move(item: Annotated[str, Form()],
               location: Annotated[str, Form()],
               quantity: Annotated[int, Form()]):
    """Mark that the item is stored in the given location.
    The quantity argument is used only for stock moves."""
    item_data = lookup(item)
    location_data = lookup(location)
    if is_inventory(item_data['barcode']):
        inv = inventory_data()
        if inv.find_one({'barcode': location_data['barcode']}):
            inv.update_one({'barcode': item_data['barcode']},
                           {'$set': {'location': int(location_data['barcode'])}},
                           upsert=True)
            return {'item_barcode': int(item_data['barcode']),
                    'item_name': item_data['name'],
                    'location_barcode': int(location_data['barcode']),
                    'location_name': location_data['name']}
        raise HTTPException(status_code=404,
                            detail=f"Location {location} not found when storing an item")
    else:
        pass                    # TODO store stock separately, using quantity

@storage_manager.post("/delete/{item}")
async def delete_item(item: str):
    """Delete an item, specified by name or barcode."""
    deledendum = lookup(item)
    if deledendum is None:
        raise HTTPException(status_code=404, detail=f"Item {item} not found for deletion")
    barcode = deledendum['barcode']
    inventory_data().delete_one({'barcode': barcode})
    return {'deleted': barcode}
