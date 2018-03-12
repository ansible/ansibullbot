#!/bin/bash

URL='https://github.com/ansible/ansible/issues?q=label%3Afeature_idea'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
