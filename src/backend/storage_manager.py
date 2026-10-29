#!/usr/bin/env python3

import decouple
import pymongo
from fastapi import FastAPI

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
async def where():
    database = ensure_database()
    return {"location": "placeholder"}

@storage_manager.get("/list")
async def list_contents():
    database = ensure_database()
    return {"location": "placeholder"}

@storage_manager.put("/store")
async def store():
    database = ensure_database()
    return {"result": "not stored"}
