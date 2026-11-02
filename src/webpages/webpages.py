#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import json
import requests

from flask import Flask, request

from expressionive.expressionive import htmltags as T
import expressionive.exprpages as exprpages

app = Flask("storage")

def titled_page(title, page):
    return str(exprpages.page_text(T.body[page],
                                   title=title))

@app.route("/")
def hello_world():
    return titled_page("Page title",
                       T.p["Page body paragraph"])

@app.route("/find")
def find():
    """Find where an item is stored."""
    res = requests.get(f"http://127.0.0.1:8000/where/{request.args.get("name")}").json()
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
