#!/bin/bash

URL='https://github.com/ansible/ansible/issues?q=is%3Aopen%20label%3Aneeds_rebase'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
