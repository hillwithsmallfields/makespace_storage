#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import datetime
import json
import requests

from flask import Flask, request
# from flask_cors import CORS

from expressionive.expressionive import htmltags as T
import expressionive.exprpages as exprpages
from expressionive.expridioms import switchable_panel

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:5000"

app = Flask("storage")

# CORS(app, origins=[WEB+"/*", API+"/*"])

# CORS(app, origins=["*"])

def finder_form():
    return T.form(action=f"{WEB}/")[
        T.fieldset[
            T.legend["Item finder"],
            T.input(type="text", name="item", id="item_to_find"),
            T.label(for_="item")["Name or barcode"],
            T.button(type='submit')["Find item"]]]

def footer():
    return [
        T.hr(),
        T.a(href=WEB)["Assets home"],
        T.p["Generated at ", datetime.datetime.now().isoformat(timespec='seconds')]
    ]

def titled_page(title, page, script="", body_params=None):
    return str(exprpages.page_text(T.body(**(body_params or {}))[finder_form(),
                                                                 page,
                                                                 footer()],
                                   title=title,
                                   script_text=script))

def get_script():
    with open("static/storage_manager.js") as instream:
        return instream.read()

@app.route("/")
def home_page():
    if (search_item := request.args.get('item')):
        return item_home(search_item)
    return titled_page(
        "Makespace asset tracker",
        T.div[
            T.h1["Makespace asset tracker home page"],
            T.div[
                T.h2["Top-level locations"],
                T.ul[[
                    T.li[T.a(href=f"{WEB}/{site}")[site]]
                    for site in requests.get(f"{API}/sites").json()['sites']]]]])

@app.route("/item/<item>")
def item_item(item):
    return item_home(item)

@app.route("/<item>")
def item_home(item=None):
    if item is None:
        print("item not given path, trying query args")
        item = request.args.get('item')
    print("item is now", item)
    res = requests.get(f"{API}/{item}").json()
    details = requests.get(f"{API}/{item}/details").json()
    equipment_class = requests.get(f"{API}/{item}/attribute/equipment class").json()['equipment class']
    types = details['types']
    item_name = res['name']
    item_type = res['type']
    links = res['links']
    contents = requests.get(f"{API}/{item}/contents").json()['contents']
    location = details['nest']
    title = f"{item_name} ({item_type})"
    page = [T.div[T.h1[title],
                  T.p[item_name, " is ",
                      [[T.span[
                          f"{layer['preposition']} ",
                          T.a(href=f"{WEB}/{layer['name']}")[layer['name']]] for layer in location]],
                      " and is ", equipment_class, " equipment."]]]
    page.append(T.div[T.h2["Types"],
                      T.ul[[T.li[T.a(href=f"{WEB}/{t}/type")[t]] for t in types]]])
    if contents:
        page.append(T.div[T.h2["Contents"],
                          T.ul[[
                              T.li[T.a(href=f"{WEB}/{dweller['name']}")[dweller['name']]]
                              for dweller in contents
                          ]]])
    # TODO: show the types, with a link on each to get the details of the type, which will also have a link to list everything of that type
    # TODO: use the 'fits' attribute to construct where something can be moved to
    page.append(T.div[T.h2["API links"],
                      T.ul[[T.li[T.a(href=value)[key]]
                             for key, value in links.items()]]])
    return titled_page(title, page)

@app.route("/<typename>/type")
def type_details(typename):
    return titled_page("Type details",
                       T.div[T.p["Details of " + typename],
                             T.a(href=f"{WEB}/{typename}/list")["List all things of type ", typename]
                             ])

@app.route("/<typename>/list")
def type_list(typename):
    things = requests.get(f"{API}/{typename}/list_type").json()#['types']
    return titled_page("Type list",
                       T.div[T.p["List of " + typename],
                             T.ul[[
                                 T.li[T.a(href=f"{WEB}/{thing['name']}")[thing['name']]]
                                 for thing in things
                                 ]]
                             ])

@app.route("/<item>/details")
def details(item):
    return titled_page("Details",
                       T.div["details of ", item, " will go here."])

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
