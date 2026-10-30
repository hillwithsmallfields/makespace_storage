#!/usr/bin/env python3

"""Web front-end for the storage management system."""

import requests

from flask import Flask

from expressionive.expressionive import htmltags as T
import expressionive.exprpages as exprpages

app = Flask("storage")

@app.route("/")
def hello_world():
    return exprpages.page_text(
        T.html[T.head[T.title["Page title"]],
               T.body[T.p["Page body paragraph"]]])

@app.route("/find")
def find():
    """Find where an item is stored."""
    pass

@app.route("/describe")
def describe():
    """Describe an item."""
    pass

@app.route("/store")
def store():
    """Indicate where an item is stored."""
    pass

@app.route("/consume")
def consume():
    """Indicate that a stock item has been used up."""
    pass
