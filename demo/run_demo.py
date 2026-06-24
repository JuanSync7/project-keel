"""
title: Demo runner
kind: demo
layer: n/a
summary: Runs the public API like a user would.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from backend import do_thing

if __name__ == "__main__":
    print(do_thing("demo", 42))
