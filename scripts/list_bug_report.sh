#!/bin/bash

URL='https://github.com/ansible/ansible/issues?q=label%3Abug_report'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
