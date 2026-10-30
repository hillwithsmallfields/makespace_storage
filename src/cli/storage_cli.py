#!/usr/bin/env python3

"""Program for using the storage system API from the command line."""

import argparse
import cmd
import decouple
import requests

def get_args():
    parser = argparse.ArgumentParser()
    return vars(parser.parse_args())

def main():
    pass

if __name__ == "__main__":
    main(**get_args())
