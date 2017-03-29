#!/bin/bash

URL='https://github.com/ansible/ansible/labels/needs_info'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
