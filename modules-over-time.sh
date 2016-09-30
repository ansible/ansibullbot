#!/bin/bash

repohome='/Users/gregdek/Desktop/ANSIBLE/REPOS/ansible'

# A simple script to determine the rough number of
# individual contributors to Ansible. Set $repohome
# to wherever your git checkouts are.

# Get the latest bits
cd $repohome/ansible-modules-core
git pull

# This ugly one-liner gets the first commit date of every .py file
# in the repo, excluding __init__ files and deprecated files.

# find . -name "*.py" | grep -v '__init__' | grep -v '/_' | xargs -I {} sh -c "echo {}; git log --format='%ai' {} | sort | head -n 1" >> /tmp/modules-dates.txt

# Now let's take that file and chop it up a bit.
# perl -pi.bak1 -e 's/py\n/py /g;' /tmp/modules-dates.txt

# Now let's spit out the final list.
perl -ne 'print "$2 $1\n" if m/([^\s]*) ([^\s]*)/;' /tmp/modules-dates.txt | sort
