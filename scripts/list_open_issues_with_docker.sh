#!/bin/bash

URL='https://github.com/ansible/ansible/labels/docker'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
