#!/bin/bash

PYTHONPATH=($pwd) nosetests -v --nocapture $@
