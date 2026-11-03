#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import json
import requests

from flask import Flask, request
from flask_cors import CORS

from expressionive.expressionive import htmltags as T
import expressionive.exprpages as exprpages
from expressionive.expridioms import switchable_panel

API = "http://127.0.0.1:8000"

app = Flask("storage")
CORS(app, origins=[API+"/*"])

def titled_page(title, page, script="", body_params=None):
    return str(exprpages.page_text(T.body(**(body_params or {}))[page],
                                   title=title,
                                   script_text=script))

def get_script():
    with open("static/storage_manager.js") as instream:
        return instream.read()

def finder_form():
    return T.div()[
        T.form()[
            T.fieldset[
                T.legend["Item finder"],
                T.input(type="text", name="item", id="item"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="find_item();")["Find item"]]],
        T.p["Item location: ", T.span(id="location")[""]]]

def details_form():
    return T.div()[
        T.form()[
            T.fieldset[
                T.legend["Detail inspector"],
                T.input(type="text", name="item", id="item"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="inspect_item();")["Inspect item"]]],
        T.p["Item details: ", T.span(id="location")[""]]]

def placer_form():
    return T.div()[
        T.form()[
            T.fieldset[
                T.legend["Item placer"],
                T.input(type="text", name="item", id="item"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.input(type="text", name="item", id="place"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="place_item();")["Place item"]]],
        T.p["Item registered at location: ", T.span(id="location")[""]]]

@app.route("/")
def one_page_app():
    return titled_page("Storage manager",
                       T.div[switchable_panel("one_page_app_switcher",
                                              panels={'Find': finder_form(),
                                                      'Details': details_form(),
                                                      'Store': placer_form()},
                                              labels={'Find': "Find",
                                                      'Details': "Show",
                                                      'Store': "Store"},
                                              order=['Find', 'Details', 'Store'],
                                              initial='Find',
                                              buttons_side='left')],
                       script=get_script(),
                       body_params={'onload': "startup();"})

@app.route("/find")
def find():
    """Find where an item is stored."""
    res = requests.get(f"{API}/where/{request.args.get("name")}").json()
    return titled_page("Search result",
                       T.p[res['item']['name'], " is ", res['location']])

@app.route("/describe")
def describe():
    """Describe an item."""
    return titled_page("Description",
                       T.p["Description will go here"])

@app.route("/store")
def store():
    """Indicate where an item is stored."""
    return titled_page("Storage confirmation",
                       T.p["Storage confirmation will go here"])

@app.route("/consume")
def consume():
    """Indicate that a stock item has been used up."""
    return titled_page("Item consumed",
                       T.p["Consumption record will go here"])

if __name__ == "__main__":
    app.run(debug=True)
