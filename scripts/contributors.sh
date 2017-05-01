#!/bin/bash

repohome='/Users/gregdek/Desktop/ANSIBLE/REPOS/ansible'

# A simple script to determine the rough number of
# individual contributors to Ansible. Set $repohome
# to wherever your git checkouts are.

cd $repohome/ansible
git pull
git log --all --format='%cN' | sort -u > /tmp/ansible-contributors
cd $repohome/ansible-modules-core
git pull
git log --all --format='%cN' | sort -u >> /tmp/ansible-contributors
cd $repohome/ansible-modules-extras
git pull
git log --all --format='%cN' | sort -u >> /tmp/ansible-contributors
sort -u /tmp/ansible-contributors | wc -l
