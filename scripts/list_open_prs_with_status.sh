#!/bin/bash

URL='https://github.com/ansible/ansible/issues?q=is%3Aopen%20is%3Apr%20status%3A'
PYTHONPATH=$(pwd) scripts/scrape_github_issues_url $URL
