#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import datetime
import json
import re
import requests

from flask import Flask, request, redirect
# from flask_cors import CORS

from expressionive.expressionive import htmltags as T
import expressionive.exprpages as exprpages
from expressionive.expridioms import switchable_panel

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:5000"

app = Flask("storage")

FIELDS_REFERENCE = "https://github.com/hillwithsmallfields/makespace_storage/blob/trunk/doc/reference/fields.md"

# CORS(app, origins=[WEB+"/*", API+"/*"])

# CORS(app, origins=["*"])

def finder_form():
    return T.form(action="/", class_='finder_form')[
        T.fieldset[
            T.legend["Item finder"],
            T.label(for_="item")["Name or barcode"],
            T.input(type="text", name="item", id="item_to_find", autofocus=True),
            T.button(type='submit')["Find item"]]]

def header():
    return [finder_form()]

def footer():
    return [T.hr(),
            T.p["[", T.a(href=WEB)["Assets home"], "][",
                T.a(href="https://web.makespace.org/")["Makespace"], "][",
                T.a(href="https://sites.google.com/makespace.org/equipment/home")["Equipment"], "][",
                T.a(href="https://web.makespace.org/training/")["Training"], "]"],
            T.p["Generated at ", datetime.datetime.now().isoformat(timespec='seconds')]]

def titled_page(title, page, script="", body_params=None):
    return str(exprpages.page_text(T.body(**(body_params or {}))[header(),
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
    """Get JSON from the API server."""
    response = requests.get(f"{API}{path}", params=params or {})
    if response.status_code == 200:
        return response.json()
    raise requests.exceptions.HTTPError(f"Could not get {path}: {response.status_code} with params {params}")

def post_json(path, params=None):
    """Post JSON to the API server."""
    response = requests.post(f"{API}{path}", params=params or {})
    if response.status_code == 200:
        return response.json()
    raise requests.exceptions.HTTPError(f"Could not post {path}: {response.status_code} with params {params}")

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
        T.div[T.h1["Makespace asset tracker home page"],
              T.div[T.h2["Top-level locations"],
                    T.ul[[T.li[T.span(class_="location")[T.a(href=f"/{site}")[site]]]
                          for site in get_json("/sites")['sites']]]],
              T.div[T.h2["Top-level types"],
                    T.ul[[T.li[T.span(class_="type")[T.a(href=tlt)[tlt.title()]]]
                          for tlt in get_json("/top-level-types")['types']]]]])

@app.route("/item/<item>")
def item_item(item):
    """Serve the home page for an item."""
    return item_home(item)

def summarise_one_location(location):
    """Summarise a location."""
    return [[T.span(class_="loc_layer")[
        f"{layer['preposition']} ",
        T.a(href=f"/{layer['name']}")[layer['name']]]
             for layer in location]]

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

def just_name(name):
    """A field name can be given as just a string, or as a list beginning with the string.
    The second item of the list will be the hover text."""
    return (name if isinstance(name, str) else name[0])

def name_text(name, reference=None):
    """Return the expressionive structure to display a name.

    If the name is a list of the actual name and an explanation, make
    a hover text from the explanation.

    If a reference page is given, make a link to an anchor for the
    name in that page."""

    def polite_form(name, reference=None):
        text = name.replace('_', ' ')
        return T.a(href=f"{reference}#{name.lower()}", target='_blank')[text] if reference else text

    return (polite_form(name, reference)
            if isinstance(name, str)
            else T.span(class_='name')[polite_form(name[0], reference),
                                       T.span(class_='explanation')[name[1]]])

def just_names(names):
    """Like `just_name` but for a list of names."""
    return [just_name(name) for name in names]

def supplies_value(descr, value, item_dict):
    return [T.a(href=f"/item/{si}")[si]
            for si in [s.strip() for s in value.split(';')]]

def item_name(item):
    return get_json(f"/attribute/{item}/name")['name'] if item else "The world"

def location_value(descr, value, item_dict):
    # For now, it's the same result as not having a display handler,
    # but I'd like it to have a hover text giving the full location.
    # But really, it's got a handler because I want it to have one for
    # the edit form.
    location_name = item_name(value)
    return T.a(href=location_name)[location_name]

def type_value(descr, value, item_dict):
    # For now, it's the same result as not having a display handler,
    # but I'd like it to have a hover text giving the full hierarchical type.
    # But really, it's got a handler because I want it to have one for
    # the edit form.
    return T.a(href=item_dict.get(just_name(descr)+"_URL"))[value]

def edit_supplies(descr, value, item_dict):
    # For now, it's the same result as not having an edit handler, but
    # I'd like it to put in multiple <select>s plus a way of adding
    # and deleting entries.  Or perhaps a list of checkboxes and a way
    # of adding things?
    return T.input(type='text',
                   name=(name := just_name(descr)),
                   value=item_dict.get(name, ""))

def edit_location(descr, value, item_dict):
    """Make an edit form part for the location of an item.
    Only the locations in which that type of item can be stored are presented."""
    field_name = just_name(descr) # for example, "location"
    name = item_dict['name'] # just_name(descr)
    value = item_dict.get(just_name(descr), "")
    item_type = item_dict.get('type')
    old_location_name = item_name(value)
    # old_location_name = value
    return (T.a(href=f"{FIELDS_REFERENCE}#fixed", target='_blank')["This item is not movable"]
            if get_json(f"/attribute/{name}/fixed")['fixed']
            else (T.select(name=name, id=name)[
                    [T.option(value=opt,
                              # I have to not supply 'selected' at all, as selected=False doesn't work
                              **({'selected': 'true'} if old_location_name==opt else {}))[opt]
                     for opt in get_json(f"/locations_for/{item_type}")['locations']]]))

def edit_type(descr, value, item_dict):
    # For now, it's the same result as not having an edit handler, but
    # I'd like it to put in multiple <select>s plus a way of adding
    # and deleting entries.  Or perhaps a list of checkboxes and a way
    # of adding things?
    return T.input(type='text',
                   name=(name := just_name(descr)),
                   value=item_dict.get(name, ""))

NAME_DISPLAY_HANDLERS = {
    'supplies': supplies_value,
    'location': location_value,
    'type': type_value,
}

EDIT_HANDLERS = {
    'supplies': edit_supplies,
    'location': edit_location,
    'type': edit_type,
}

def linked_value(descr, value, item_dict):
    """Return the expressionive structure for an attribute value cell.
    Special handling is applied as relevant."""
    name = just_name(descr)
    return (NAME_DISPLAY_HANDLERS[descr[2]](descr, value, item_dict)
            if isinstance(descr, list) and len(descr) >= 3
            else (T.a(href=item_dict.get(name+"_URL"))[value]
                  if name+"_URL" in item_dict
                  else value))

def extra_form_fields(fieldnames, values_dict):
    """Return a table of form fields for setting details of an item.
    See `extra_display_fields` for details of what can be in a descriptor."""
    return [[T.tr[T.td(class_='attr_table_label')[name_text(descr, FIELDS_REFERENCE)],
                   T.td[EDIT_HANDLERS[descr[2]](descr, values_dict.get(name, ""), values_dict)
                         if isinstance(descr, list) and len(descr) >= 3
                         else T.input(type='text',
                                      name=(name := just_name(descr)),
                                     value=values_dict.get(name, ""))]]
            for descr in fieldnames]]

def extra_display_fields(fieldnames, item_dict):
    """Return a table of attribute names and values.
    Each name may be a string, or a list of strings, thus:
    - the actual name
    - a help string giving more information
    - optionally, the name of a display handler bound in NAME_DISPLAY_HANDLERS
      and an edit handler bound in EDIT_HANDLERS."""
    return [T.table[[T.tr[T.td(class_='attr_table_label')[name_text(descr, FIELDS_REFERENCE)],
                          T.td(class_='attr_table_value')[linked_value(descr, value, item_dict)]]
                     for descr in fieldnames
                     if ((not (name := just_name(descr)).endswith("_URL"))
                         and (value := item_dict.get(name)) is not None)]]]

def type_selector(kind='inventory-'):
    return [[T.option(value=typename)[typename]
             for typename in sorted(get_json(f"/{kind}types")['types'])]]

def inventory_create_or_edit_form(item_name="", barcode=0, get_existing=True):
    extra_fields = get_json("/suggested_fields")['inventory']
    return T.div[T.form(action="/new_inventory", method='post')[
        T.table[T.tr[T.td(class_='attr_table_label')[T.label(for_='barcode')["Barcode:"]],
                     T.td[T.input(type='text', name='barcode', value=str(barcode))]],
                T.tr[T.td(class_='attr_table_label')[T.label(for_='item_name')["Item name:"]],
                     T.td[T.input(type='text', name='item_name', value=item_name)]],
                T.tr[T.td(class_='attr_table_label')[T.label(for_='item_type')["Item type:"]],
                     T.td[T.select(name='item_type', id='item_type')[type_selector()]]],
                extra_form_fields(extra_fields,
                                  (get_json(f"/attributes/{item_name}/{';'.join(extra_fields)}")
                           if get_existing
                           else {}))],
        T.button(type='submit')["Create inventory item"]]]

def stock_type_create_or_edit_form(item_name="", get_existing=True):
    extra_fields = get_json("/suggested_fields")['stock']
    return T.div[T.form(action="/new_stock_item", method='post')[
        T.table[T.tr[T.td(class_='attr_table_label')[T.label(for_='item_name')["Stock type name"]],
                     T.td[T.input(type='text', name='item_name', value=item_name)]],
                extra_form_fields(get_json("/suggested_fields")['stock'],
                                  (get_json(f"/attributes/{item_name}/{';'.join(extra_fields)}")
                           if get_existing
                           else {}))],
        T.button(type='submit')["Create stock item type"]]]

def inventory_type_create_or_edit_form(item_name, get_existing=True):
    return T.div[
        T.form(action="/new_type", method='post')[
            T.table[T.tr[T.td(class_='attr_table_label')[T.label(for_='type_name')["Type name"]],
                         T.td[T.input(type='text', name='type_name', id='type_name', value=item_name)]],
                    T.tr[T.td(class_='attr_table_label')[T.label(for_='parent_type')["Parent type:"]],
                         T.td[T.select(name='parent_type', id='parent_type')[type_selector()]]]],
        T.button(type='submit')["Create type"]]]

def stock_link_barcode_to_stock_type_form(item_name, barcode, get_existing=True):
    return T.div[
        T.p["""Stock items are known by their stock type name, and not by barcode, """,
            """because there may be multiple barcodes for each stock type.""",
            """This form is to link a new barcode to an existing stock type."""],
        T.form(action="/link_stock_type", method='post')[
        T.table[T.tr[T.td[T.label(for_='barcode')["Barcode:"]],
                     T.td[T.input(type='text', name='barcode', value=str(barcode))]],
                T.tr[T.td[T.label(for_='type_name')["Type name:"]],
                     T.td[T.select(name='type_name', id='type_name')[[T.option["New stock type"]] + type_selector(kind='stock-')]]],
                T.tr[T.td[T.label(for_='new_stock_type')["New stock type"]],
                     T.td[T.input(type='text', name='new_stock_type', value="")]]],
        T.button(type='submit')["Link stock type"]]]

@app.route("/item/<item>/new/<hint>")
def create_something_page(item, hint):
    numeric = re.match("^[0-9]+$", item)
    barcode = int(item) if numeric else None
    if numeric:
        item = ""
    return titled_page(
        "Create item",
        T.div[T.p[f'"{item or str(barcode)}" (type {type(barcode)} was not found in any of our collections.'],
              T.p["This is your chance to add it to the appropriate collection."],
              switchable_panel(switcher_id='creator_switcher',
                               panels={'inventory': inventory_create_or_edit_form(item, barcode, False),
                                       'type': inventory_type_create_or_edit_form(item, False),
                                       'stocktype': stock_type_create_or_edit_form(item, False),
                                       'stockcode': stock_link_barcode_to_stock_type_form(item, barcode, False)},
                               labels={'inventory': "Inventory item",
                                       'type': "Inventory type",
                                       'stocktype': "Stock type",
                                       'stockcode': "Link barcode to stock type"},
                               order=['inventory', 'type', 'stocktype', 'stockcode'],
                               buttons_side='top',
                               initial=hint or 'inventory')])

@app.route("/new_type", methods=['post'])
def new_type():
    name = request.form.get('name')
    item_type = request.form.get('item_type')
    j = post_json("/new_type", params={'name': name, 'item_type': item_type})
    return titled_page("Creating type", T.p["Creating type with result ", str(j)])

@app.route("/new_stock", methods=['post'])
def new_stock():
    j = post_json("/new_stock")
    return titled_page("Creating stock", T.p["Creating stock with result ", str(j)])

@app.route("/new_inventory", methods=['post'])
def new_inventory():
    item_name = request.form.get('item_name')
    item_type = request.form.get('item_type')
    j = post_json("/new_inventory", params={'item_name': item_name, 'item_type': item_type})
    return titled_page("Creating inventory", T.p["Creating inventory with result ", str(j)])

def get_subtypes(ty):
    return [st for st in get_json(f"/subtypes/{ty}") if st != ty]

def get_parent_types(ty):
    return [pt for pt in get_json(f"/parent_types/{ty}") if pt != ty]

def unnumbered_list(elements, path_prefix="", sort_by=None):
    return T.ul[[T.li[T.a(href=path_prefix+elt)[elt]] for elt in
                 (sorted(elements, key=sort_by)
                  if sort_by is not None
                  else elements)]]

def add_related_types(item, page):
    if (parent_types := get_parent_types(item)):
        print("parent types are", parent_types)
        page.append(T.div(class_='parent_types')[
            T.h2[f'Parent types of "{item}"'],
            unnumbered_list(parent_types, path_prefix="/")])
    if (subtypes := get_subtypes(item)):
        page.append(T.div(class_='subtypes')[
            T.h2[f'Subtypes of "{item}"'],
            unnumbered_list(subtypes, sort_by=lambda x: x)])

def search_results_or_create(item, item_fetch_result):
    """Produce a page for when an item was not found.
    List ambiguous results, or offer to create an item."""

    search_results = get_json("/search", params={'pattern': item})
    page = [T.h1["No exact match"],
            T.p[f'There was no exact match for "{item}".']]
    if any(search_results.values()):
        page.append([T.p["The following partial matches were found:"],
                     [[[T.h2[group.title()],
                        T.ul[[T.li[T.a(href=f"/item/{pm['name']}")[pm['name']]] for pm in matches]]]
                       for group, matches in search_results.items()
                       if matches]]])
    page.append([T.p["If none of those is what you meant, you can now ",
                     T.a(href=item_fetch_result['links']['new'].replace(API, WEB))[f"create {item}"],
                     "."]])

    return titled_page(f"Item {item} not found", page)

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

@app.route("/update_inventory_item", methods=['post'])
def update():
    referring_page = request.form.get('referring_page')
    post_json("/update_inventory_item", params={
        k: v
        for k, v in request.form.items()
        if k not in ['referring_page']})
    return redirect(referring_page)

@app.route("/update_stock", methods=['post'])
def update_stock():
    referring_page = request.form.get('referring_page')
    action = request.form.get('action')
    delta = request.form.get('delta')
    stock_item = request.form.get('stock_item')
    location = request.form.get('location')
    existing = request.form.get('existing')
    post_json("/update_stock", params={
        'action': action,
        'delta': delta,
        'stock_item': stock_item,
        'location': location,
        'existing': existing,
        'referring_page': referring_page,
    })
    return redirect(referring_page)

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

def add_stock_table(page, item):
    # page.append(T.p[str(get_json(f"/levels/{item}"))])
    page.append(T.table[
        T.tr[T.th["Location"], T.th["Quantity"], T.th["Adjust by"]],
        [[T.tr[
            T.td(class_="stock_item attr_table_label")[
                T.a(href=f"/stock/{location}")[
                    get_json(f"/name/{location}")['name']
                ]],
            T.td[str(count)],
            T.td[T.form(action="/update_stock", method='post')[
                T.input(type='text', name='delta', value="1"),
                T.input(type='submit', name='action', value='-'),
                T.input(type='submit', name='action', value='='),
                T.input(type='submit', name='action', value='+'),
                T.input(type='hidden', name='referring_page', value=request.url),
                T.input(type='hidden', name='stock_item', value=item),
                T.input(type='hidden', name='location', value=location),
                T.input(type='hidden', name='existing', value=str(count)),
            ]]]
          for location, count in get_json(f"/levels/{item}").items()]]])

def add_details_panels(page, item_name, kind='inventory'):
    extra_fields = get_json("/suggested_fields")[kind]
    extra_values = get_json(f"/attributes/{item_name}/{';'.join(just_names(extra_fields))}")
    page.append(T.div[T.h2["Further details"],
                      switchable_panel(switcher_id='display_or_edit_switcher',
                                       panels={'display': extra_display_fields(extra_fields, extra_values),
                                               'edit': T.form(action=f"/update_inventory_item", method='post')[
                                                   T.table[extra_form_fields(extra_fields, extra_values)],
                                                   T.input(type='hidden', name='item_name', value=item_name),
                                                   T.input(type='hidden', name='referring_page', value=request.url),
                                                   T.input(type='submit', value="Update", method='post')
                                               ]},
                                       labels={'display': "Display",
                                               'edit': "Edit"},
                                       order=['display', 'edit'],
                                       buttons_side='top',
                                       initial='display')])

def add_supplies_details(page, supplies):
    page.append(T.div(class_='supplies')[
        T.h2["Supplies"],
        T.ul[[T.li[k, str(v)]
              for k, v in supplies.items()]]])

@app.route("/stock/<stocktype>")
def stock(stocktype):
    """Return a page about a type of stock."""
    page = [T.div[T.h1["Stock: ", stocktype]]]
    add_stock_table(page, stocktype)
    return titled_page(stocktype, page)

@app.route("/<item>")
def item_home(item=None):
    """Display the home page for an item."""
    if item is None:
        item = request.args.get('item')
    res = get_json(f"/item/{item}")
    if res['kind'] == 'unknown':

        # this is an API link, and I need to make it into a web server one
        # return redirect(res['links']['new'].replace(API, WEB))

        return search_results_or_create(item, res)

        # return titled_page("checking", T.p[res['links']['new'].replace(API, WEB)])
    if  res['kind'] == 'type':
        title = f'Type "{item}"'
        page = [T.div(class_='types')
                [T.h1[title],
                 T.h2[f'Items of type "{item}"'],
                 list_for_type(item)]]
        add_related_types(item, page)
        return titled_page(title, page)
    if res['kind'] == 'new_inventory':
        return redirect(f"/item/{res['barcode']}/new/inventory")
    if res['kind'] == 'new_stock':
        return redirect(f"/item/{res['barcode']}/new/stockcode")
    if res['kind'] == 'stock':
        return stock(item)
    details = get_json(f"/details/{item}")
    equipment_class = get_attribute(item, 'equipment class', default=None)
    types = details['types']
    item_name = res['name']
    item_type = res['type']
    links = res['links']
    contents = get_json(f"/contents/{item}")
    inventory = contents['inventory']
    location = details['nest']
    title = f"{item_name} ({item_type})"
    summary = [item_name, " is a ", res['kind'], " item ", summarise_location(location)]
    if equipment_class:
        summary.append([" and is ",
                        T.span(class_=equipment_class)[get_attribute(item, 'equipment phrase', default='of unknown type')]])
    summary.append(".")
    page = [T.div[T.h1(class_=f"{equipment_class}_equipment" or "other")[title],
                  T.p[summary]]]
    if (picture := get_attribute(item, 'picture', local_only=False)):
        page.append(T.img(src=picture))
    if (supplies := get_json(f"/supplies/{item_name}")):
        add_supplies_details(page, supplies)
    add_details_panels(page, item_name, res['kind'])
    page.append(T.div[T.h2["Types"],
                      T.ul[[T.li[T.span(class_="type")[T.a(href=f"/{t}/type")[t]]] for t in types]]])
    if inventory:
        page.append(T.div[T.h2["Inventory contents"],
                          T.ul[[T.li[T.span(class_="inv_item")[T.a(href=f"/item/{dweller['name']}")[dweller['name']]]]
                                for dweller in inventory]]])
    if (stock := contents['stock']):
        page.append(T.div[T.h2["Stock contents"],
                          T.table[[T.tr[T.td(class_="stock_item")[T.a(href=f"/stock/{dweller['name']}")[dweller['name']]],
                                        T.td[str(dweller['quantity'])]]
                                for dweller in stock]]])
    return titled_page(title, page)

@app.route("/<typename>/type")
def type_details(typename):
    page = [T.h1[f'Details of type "{typename}"']]
    add_related_types(typename, page)
    page.append([T.h2[f'Items of type "{typename}"'],
                 list_for_type(typename)])
    return titled_page(f"Type details for {typename}", T.div[page])

def list_for_type(typename):
    """Return the expressionive structure listing the things of the given typename."""
    things = get_json(f"/list_type/{typename}")
    return (T.ul[[T.li[T.a(href=f"/{thing['name']}")[thing['name']]]
                  for thing in sorted(things, key=lambda thing: thing['name'])]]
            if things
            else T.p["No items found."])

@app.route("/<typename>/list")
def type_list(typename):
    return titled_page("Type list",
                       T.div[T.p["List of " + typename],
                             list_for_type(typename)])

@app.route("/<item>/details")
def details(item):
    return titled_page("Details",
                       T.div["details of ", item, " will go here."])

if __name__ == "__main__":
    app.run(debug=True)
