#!/usr/bin/env python3

import csv
from typing import Annotated
import decouple
import pymongo
import StringIO
from fastapi import FastAPI, Query, File

storage_manager = FastAPI()

_database_client = None
_inventory = None
_types = None

def _ensure_database():
    """Ensure that we have a connection to the database."""
    global _database_client
    if not _database_client:
        _database_client = pymongo.MongoClient(
            uri,
            username=urllib.parse.quote_plus(decouple.config('user', "makers")),
            password=urllib.parse.quote_plus(decouple.config('MONGOPASSWORD', "")),
            authSource=decouple.config('database_name'),
            authMechanism='SCRAM-SHA-1')
        if _database_client is None:
            raise ConnectionError("Could not connect to database")
    return _database_client

def types():
    """Get the types collection from the database.

    Each row must define a 'name', and may define:
    - parent (a parent type)
    - preposition (if this is a type of storage location)
    """
    global _types
    if not _types:
        _types = _ensure_database()['types']
        if _types is None:
            raise ValueError("Database does not contain a type hierarchy definition")
    return _types

def inventory():
    """Get the inventory collection from the database.

    Each row must define:
    - item-id
    - name
    - type
    - location (except for top-level locations)
    """
    global _inventory
    if not _inventory:
        _inventory = _ensure_database()['inventory']
        if _inventory is None:
            raise ValueError("Database does not contain an inventory")
    return _inventory

def stock():
    """Get the stock collection from the database.

    Each row must define:
    - name
    - quantity
    - location
    """
    global _stock
    if not _stock:
        _stock = _ensure_database()['stock']
        if _stock is None:
            raise ValueError("Database does not contain a stock table")
    return _stock

def name_to_id(name):
    """Return the item_id of the item with the given name."""
    return inventory().find_one({'name': name})['item_id']

def id_to_name(item_id):
    """Return the name of an item with the given item_id."""
    return inventory().find_one({'item_id': item_id})['name']

def contents(location_id):
    """Return the contents of the given location."""
    return inventory().find({'location': location_id})

def set_location(location_id, item_id):
    """Set the location of an item."""
    inventory().update({'item_id': item_id}, {'location': location_id}, upsert=True)

def full_location(item_id):
    """Return the full hierarchical location data for an item."""
    result = []
    inv = inventory()
    while (item := inv.find_one({'item_id': item_id}).get('location')):
        result.append(enclosing)
    return result

def location_string(full_loc, sep=", "):
    """Return a string summarising the given hierarchical location data."""
    typedefs = types()
    return sep.join(f"{typesdefs[surrounder['type']]['preposition']} {surrounder['name']}"
                    for surrounder in full_loc)

@storage_manager.get("/")
async def root():
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/where/{item}")
async def where(item, full=False):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    location = full_location(item if isinstance(item, int) else id_to_name(item))
    return {"location": location if full else location_string(location)}

@storage_manager.get("/what")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    return {"matches": ["placeholder"]}

@storage_manager.get("/list")
async def list_contents(location: int):
    """List everything stored in the given location."""
    return {"location": "placeholder"}

@storage_manager.get("/map")
async def map_contents(location: int=0, items=None, format='svg'):
    """Produce a visual representation of where things are."""
    pass

@storage_manager.put("/store")
async def store(location: int,
                item: str):
    """Mark that the item is stored in the given location."""
    return {"result": "not stored"}

@storage_manager.post("/new")
async def new_item(name: str, item_type: str, item_id: int=0):
    """Create a new item.
    An item ID may be given (for example, from a barcode label you have stuck onto something)
    but if it is not given, one will be created for it."""
    database = ensure_database()
    return {'result': "not done"}

@storage_manager.post("/load")
async def load_table(table_bytes: Annotated[bytes, File()]):
    """Load data into the database from a CSV POST body."""
    for row in csv.DictReader(StringIO.StringIO(table_bytes)):
        print("got row", row)
    return {"result": "not implemented"}

@storage_manager.get("/dump")
async def dump_table():
    """Return the database contents as CSV text."""
    return {"result": "not implemented, should return CSV text instead of JSON here"}
