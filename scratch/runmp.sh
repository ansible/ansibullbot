#!/bin/bash

LOGFILE="mp.log"
PROXYURL="http://localhost:5000"
export ANSIBULLBOT_SHIPPABLE_URL=$PROXYURL
export ANSIBULLBOT_GITHUB_URL=$PROXYURL

rm -rf $LOGFILE

./triage_ansible_mp.py \
    --logfile=$LOGFILE \
    --debug \
    --verbose \
    --ignore_module_commits \
    --dry-run
