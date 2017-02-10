#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    #echo $metaf
    MC=$(jq '.labels' $metaf)
    if [[ $MC != *"c:"* ]] && [[ $MC != *"module"* ]]; then
        echo $metaf | cut -d\/ -f9
    fi
done
