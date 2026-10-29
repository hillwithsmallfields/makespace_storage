#!/usr/bin/env python3

import decouple
import pymongo
from typing import Annotated
from fastapi import FastAPI, Query

storage_manager = FastAPI()

database_client = None
inventory = None

def ensure_database():
    """Ensure that we have a connection to the database."""
    global database_client, inventory
    if not database_client:
        database_client = pymongo.MongoClient(
            uri,
            username=urllib.parse.quote_plus(db_config.get('user', "makers")),
            password=urllib.parse.quote_plus(decouple.config('MONGOPASSWORD', "")),
            authSource=db_config['database_name'],
            authMechanism='SCRAM-SHA-1')
    if not inventory:
        inventory = database_client['inventory']
        if inventory is None:
            raise ConnectionError
    return inventory

@storage_manager.get("/")
async def root():
    database = ensure_database()
    return {"message": "This is the makespace.org storage manager."}

@storage_manager.get("/where")
async def where(item):
    """Return where an item is located.
    The item may be specified by name or by id (barcode)."""
    database = ensure_database()
    return {"location": "placeholder"}

@storage_manager.get("/what")
async def what(pattern):
    """List everything with a name matching the given pattern."""
    database = ensure_database()
    return {"matches": ["placeholder"]}

@storage_manager.get("/list")
async def list_contents(location: int):
    database = ensure_database()
    return {"location": "placeholder"}

@storage_manager.put("/store")
async def store(location: int,
                items str):
    database = ensure_database()
    return {"result": "not stored"}

@storage_manager.post("/new")
async def new_item(name: str, item_type: str):
    database = ensure_database()
    return {'result': "not done"}
