#!/usr/bin/env python3

import decouple
import pymongo
from typing import Annotated
from fastapi import FastAPI, Query

storage_manager = FastAPI()

_database_client = None
_inventory = None

def inventory():
    """Ensure that we have a connection to the database."""
    global _database_client, _inventory
    if not _database_client:
        _database_client = pymongo.MongoClient(
            uri,
            username=urllib.parse.quote_plus(db_config.get('user', "makers")),
            password=urllib.parse.quote_plus(decouple.config('MONGOPASSWORD', "")),
            authSource=db_config['database_name'],
            authMechanism='SCRAM-SHA-1')
    if not _inventory:
        _inventory = database_client['inventory']
        if _inventory is None:
            raise ConnectionError
    return _inventory

def name_to_id(name):
    """Return the item_id of the item with the given name."""
    return inventory().find_one({'name': name})['item_id']

def id_to_name(item_id):
    """Return the name of an item with the given item_id."""
    return inventory().find_one({'item_id': item_id})['name']

def contents(location_id):
    """Return the contents of the given location."""
    return inventory().find({'location': location_id})

def position(location_id, item_id):
    """Set the location of an item."""
    inventory().update({'item_id': item_id}, {'location': location_id}, upsert=True)

@storage_manager.get("/")
async def root():
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/where")
async def where(item):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    return {"location": "placeholder"}

@storage_manager.get("/what")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    return {"matches": ["placeholder"]}

@storage_manager.get("/list")
async def list_contents(location: int):
    return {"location": "placeholder"}

@storage_manager.put("/store")
async def store(location: int,
                items str):
    return {"result": "not stored"}

@storage_manager.post("/new")
async def new_item(name: str, item_type: str):
    database = ensure_database()
    return {'result': "not done"}
