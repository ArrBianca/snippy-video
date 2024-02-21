#! /usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
from argparse import ArgumentParser
from re import escape
from subprocess import run
from sys import exit

import argcomplete


def go():
    parser = ArgumentParser()

    parser.add_argument("input", help="The video file input")
    # I don't know if these guys are inclusive or exclusive ⬇️
    parser.add_argument("start_ts", help="Starting timestamp of the clip in the form [[HH:]MM:]SS[.MLS] or START")
    parser.add_argument("end_ts", help="Ending timestamp of the clip in the form [[HH:]MM:]SS[.MLS] or END")

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

# Take the video apart to pngs into a temp folder. gifski them back together.
#what could go wrogn
