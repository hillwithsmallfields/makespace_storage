#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import datetime
import json
import requests

from flask import Flask, request, redirect
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
    return T.form(action="/")[
        T.fieldset[
            T.legend["Item finder"],
            T.label(for_="item")["Name or barcode"],
            T.input(type="text", name="item", id="item_to_find"),
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
                                   script_text=get_script(),
                                   style_text=get_style()))

def get_script():
    with open("static/storage_manager.js") as instream:
        return instream.read()

def get_style():
    with open("static/storage_manager.css") as instream:
        return instream.read()

def get_json(path, params=None):
    """Get JSON about an item from the API server."""
    response = requests.get(f"{API}{path}",
                            params=params or {})
    if response.status_code == 200:
        return response.json()
    raise requests.exceptions.HTTPError(f"Could not get {path}: {response.status_code}")

def get_attribute(item, attribute, local_only=False, default=None):
    return get_json(f"/attribute/{item}/{attribute}",
                    params=({'local_only': True}
                            if local_only
                            else {})).get(attribute, default)

@app.route("/")
def home_page():
    """Return the top-level page for the site, if no search string was given.
    Otherwise, look up the search string and return the page for the result."""
    if (search_item := request.args.get('item')):
        return item_home(search_item)
    return titled_page(
        "Makespace asset tracker",
        T.div[
            T.h1["Makespace asset tracker home page"],
            T.div[
                T.h2["Top-level locations"],
                T.ul[[
                    T.li[T.a(href=f"/{site}")[site]]
                    for site in get_json("/sites")['sites']]]],
            T.div[
                T.h2["Top-level types"],
                T.ul[[
                    T.li[T.a(href=tlt)[tlt]]
                    for tlt in get_json("/top-level-types")['types']
                    ]]]])

@app.route("/item/<item>")
def item_item(item):
    """Serve the home page for an item."""
    return item_home(item)

def summarise_one_location(location):
    """Summarise a location."""
    return [[T.span[f"{layer['preposition']} ",
                    T.a(href=f"/{layer['name']}")[layer['name']]] for layer in location]]

def summarise_location(location):
    """Summarise a location or collection of locations."""
    if not location:
        return "at large in the world"
    if isinstance(location[0], dict):
        return summarise_one_location(location)
    locs = []
    for loc in location:
        if locs:
            locs.append(" and ")
        locs.append(summarise_one_location(loc))
    return locs

def type_selector(kind='inventory-'):
    return [[T.option(value=typename)[typename]
             for typename in sorted(get_json(f"/{kind}types")['types'])]]

def inventory_creator_form(item_name):
    return T.div[T.form(action="/new_inventory", method='post')[
        T.label(for_='item_name')["Item name:"],
        T.input(type='text', name='item_name', value=item_name),
        T.br,
        T.label(for_='item_type')["Item type:"],
        T.select(name='item_type', id='item_type')[type_selector()],
        T.br,
        T.button(type='submit')["Create inventory item"]]]

def stock_creator_form(item_name):
    return T.div[T.form(action="/new_stock_item", method='post')[
        T.label(for_='item_name')["Stock item name:"],
        T.input(type='text', name='item_name', value=item_name),
        T.br,
        T.label(for_='item_type')["Item type:"],
        T.select(name='item_type', id='item_type')[type_selector(kind='stock-')],
        T.br,
        T.button(type='submit')["Create stock item type"]]]

def type_creator_form(item_name):
    return T.div[T.form(action="/new_type", method='post')[
        T.label(for_='type_name')["Type name:"],
        T.input(type='text', name='type_name', value=item_name),
        T.br,
        T.label(for_='parent_type')["Parent type:"],
        T.select(name='parent_type', id='parent_type')[type_selector()],
        T.br,
        T.button(type='submit')["Create type"]]]

@app.route("/item/<item>/new")
def create_something_page(item):
    return titled_page(f"Creating {item}",
                       T.div["Creating a specific kind of thing"]
                       if 'type' in request.args
                       else (T.div[
                               switchable_panel(switcher_id='creator_switcher',
                                                panels={
                                                    'inventory': inventory_creator_form(item),
                                                    'stock': stock_creator_form(item),
                                                    'type': type_creator_form(item),
                                                },
                                                labels={
                                                    'inventory': "Inventory item",
                                                    'stock': "Stock item",
                                                    'type': "Type",
                                                },
                                                order=['inventory', 'stock', 'type'],
                                                buttons_side='top',
                                                initial='inventory')]))

@app.route("/new_type", methods=['post'])
def new_type():
    j = get_json("/new_type")
    return titled_page("Creating type", T.p["Creating type with result ", str(j)])

@app.route("/new_stock", methods=['post'])
def new_stock():
    j = get_json("/new_stock")
    return titled_page("Creating stock", T.p["Creating stock with result ", str(j)])

@app.route("/new_inventory", methods=['post'])
def new_inventory():
    j = get_json("/new_inventory")
    return titled_page("Creating inventory", T.p["Creating inventory with result ", str(j)])

def get_subtypes(ty):
    return [st for st in get_json(f"/subtypes/{ty}") if st != ty]

def get_parent_types(ty):
    return [pt for pt in get_json(f"/parent_types/{ty}") if pt != ty]

def unnumbered_list(elements):
    return T.ul[[T.li[T.a(href=elt)[elt]] for elt in elements]]

def add_related_types(item, page):
    if (parent_types := get_parent_types(item)):
        page.append(T.div(class_='parent_types')[
            T.h2["Parent types"],
            unnumbered_list(parent_types)])
    if (subtypes := get_subtypes(item)):
        page.append(T.div(class_='subtypes')[
            T.h2["Subtypes"],
            unnumbered_list(subtypes)])

@app.route("/<item>")
def item_home(item=None):
    if item is None:
        item = request.args.get('item')
    res = get_json(f"/item/{item}")
    if res['kind'] == 'unknown_new':
        # this is an API link, and I need to make it into a web server one
        return redirect(res['links']['new'].replace(API, WEB))
        # return titled_page("checking", T.p[res['links']['new'].replace(API, WEB)])
    if  res['kind'] == 'type':
        title = f"Type {item}"
        page = [T.div(class_='types')
                [T.h1[title]],
                T.p[T.a(href=f"/{item}/list")[f"List objects of type {item}"]]]
        add_related_types(item, page)
        return titled_page(title, page)
    details = get_json(f"/details/{item}")
    equipment_class = get_attribute(item, 'equipment class', default=None)
    types = details['types']
    item_name = res['name']
    item_type = res['type']
    links = res['links']
    contents = get_json(f"/contents/{item}")
    inventory = contents['inventory']
    stock = contents['stock']
    location = details['nest']
    title = f"{item_name} ({item_type})"
    summary = [item_name, " is ",
               summarise_location(location)]
    if equipment_class:
        summary.append([" and is ",
                        T.span(class_=f"{equipment_class}_equipment")[equipment_class,
                                                                      " equipment"]])
    summary.append(".")
    page = [T.div[T.h1(class_=f"{equipment_class}_equipment" or "other")[title],
                  T.p[summary]]]
    if (picture := get_attribute(item, 'picture', local_only=False)):
        page.append(T.img(src=picture))
    if res['kind'] == 'stock':
        page.append(T.table[
            T.tr[T.th["Location"], T.th["Quantity"], T.th["Adjust by"]],
            [[
                T.tr[
                    T.th[name],
                    T.td[str(count)],
                    T.td[T.form(action="/update_stock")[
                        T.input(type='text', value="1"),
                        T.input(type='submit', value='remove'),
                        T.input(type='submit', value='set'),
                        T.input(type='submit', value='add'),
                    ]]
                ]
                for name, count in get_json(f"/levels/{item}").items()
            ]]
        ])
    page.append(T.div[T.h2["Types"],
                      T.ul[[T.li[T.a(href=f"/{t}/type")[t]] for t in types]]])
    if inventory:
        page.append(T.div[T.h2["Inventory contents"],
                          T.ul[[T.li[T.a(href=f"/{dweller['name']}")[dweller['name']]]
                                for dweller in inventory]]])
    if stock:
        page.append(T.div[T.h2["Stock contents"],
                          T.ul[[T.li[T.a(href=f"/{dweller['name']}")[dweller['name']]]
                                for dweller in stock]]])
    # TODO: show the types, with a link on each to get the details of the type, which will also have a link to list everything of that type
    # TODO: use the 'fits' attribute to construct where something can be moved to
    page.append(T.div[T.h2["API links"],
                      T.ul[[T.li[T.a(href=value)[key]]
                             for key, value in links.items()]]])
    return titled_page(title, page)

@app.route("/<typename>/type")
def type_details(typename):
    page = [T.p["Details of type ", typename]]
    add_related_types(typename, page)
    page.append(T.p[T.a(href=f"/{typename}/list")["List all things of type ", typename]])
    return titled_page("Type details",
                       T.div[page])

@app.route("/<typename>/list")
def type_list(typename):
    things = get_json(f"/list_type/{typename}")#['types']
    return titled_page("Type list",
                       T.div[T.p["List of " + typename],
                             T.ul[[
                                 T.li[T.a(href=f"/{thing['name']}")[thing['name']]]
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
    res = get_json(f"/where/{request.args.get("name")}")
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
