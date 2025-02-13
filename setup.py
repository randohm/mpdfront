#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

def read_requirements(file):
    with open(file) as f:
        return f.read().splitlines()

setup(
    name = "mpdfront",
    version = "0.2.0",
    license = "Apache License v2.0",
    url = "https://github.com/randohm/mpdfront.git",
    description = "Frontend for MPD",
    long_description = open("README.md").read(),
    packages = find_packages(),
    install_requires=read_requirements("requirements.txt"),
    scripts = ['bin/mpdfront'],
    data_files = [ ('share/mpdfront', [ 'style.css', 'logging.yml' ]) ],
)
