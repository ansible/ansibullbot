#!/bin/bash

CACHEDIR=~/.ansibullbot/cache/shippable.runs/.raw

find $CACHEDIR -type f -atime +2 | xargs rm -f
