#!/usr/bin/env python3
"""Run the screening funnel on synthetic data. No network, no vendor keys."""

import sys

from oneil.cli import main

if __name__ == "__main__":
    sys.exit(main(["--demo"]))
