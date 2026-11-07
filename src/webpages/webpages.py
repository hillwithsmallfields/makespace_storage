#!/usr/bin/env python3

"""Web front-end for the storage management system."""

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
                T.input(type="text", name="item_to_find", id="item_to_find"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="find_item();")["Find item"]]],
        T.p["Item location: ", T.span(id="location")[""]]]

def details_form():
    return T.div()[
        T.form()[
            T.fieldset[
                T.legend["Item inspector"],
                T.input(type="text", name="item_to_inspect", id="item_to_inspect"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="inspect_item();")["Inspect item"]]],
        T.div(class_='inspection_details')[
            T.p["Item location: ", T.span(id="location")[""]],
            T.p["Item types: ", T.span(id="types")[""]],
        ]]

def placer_form():
    return T.div()[
        T.form()[
            T.fieldset[
                T.legend["Item placer"],
                T.input(type="text", name="item_to_store", id="item_to_store"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.input(type="text", name="place", id="place"),
                T.label(for_="item")["Name or barcode"],
                T.br,
                T.button(type='button', onclick="place_item();")["Place item"]]],
        T.p["Item registered at location: ", T.span(id="location")[""]]]

@app.route("/")
def one_page_app():
    return titled_page("Storage manager",
                       T.div[switchable_panel("one_page_app_switcher",
                                              panels={'Find': finder_form(),
                                                      'Inspect': details_form(),
                                                      'Store': placer_form()},
                                              labels={'Find': "Find",
                                                      'Inspect': "Inspect",
                                                      'Store': "Store"},
                                              order=['Find', 'Inspect', 'Store'],
                                              initial='Find',
                                              buttons_side='left')],
                       script=get_script(),
                       body_params={'onload': "startup();"})

@app.route("/<item>")
def item_home(item):
    res = requests.get(f"{API}/{item}").json()
    details = requests.get(f"{API}/{item}/details").json()
    equipment_class = requests.get(f"{API}/{item}/attribute/equipment class").json()['equipment class']
    item_name = res['name']
    item_type = res['type']
    links = res['links']
    contents = requests.get(f"{API}/{item}/contents").json()['contents']
    location = requests.get(links['where']).json()['nest']
    title = f"{item_name} ({item_type})"
    page = [T.div[T.h1[title],
                  T.p[item_name, " is ",
                      [[T.span[
                          f"{layer['preposition']} ",
                          T.a(href=f"{WEB}/{layer['name']}")[layer['name']]] for layer in location]],
                      " and is ", equipment_class, " equipment."]]]
    if contents:
        page.append(T.div[T.h2["Contents"],
                          T.ul[[
                              T.li[T.a(href=f"{WEB}/{dweller['name']}")[dweller['name']]]
                              for dweller in contents
                          ]]])
    page.append(T.div[T.h2["API links"],
                      T.ul[[T.li[T.a(href=value)[key]]
                             for key, value in links.items()]]])
    return titled_page(title, page)

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
