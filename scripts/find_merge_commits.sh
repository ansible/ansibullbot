#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    #echo $metaf
    MC=$(jq '.merge_commits' $metaf)
    if [[ $MC == "true" ]]; then
        echo $metaf $MC
    fi
done
