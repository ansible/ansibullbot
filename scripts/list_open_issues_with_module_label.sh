#!/bin/bash

PYTHONPATH=$(pwd) scripts/scrape_github_issues_url 'https://github.com/ansible/ansible/issues?q=is%3Aopen%20label%3Amodule'
