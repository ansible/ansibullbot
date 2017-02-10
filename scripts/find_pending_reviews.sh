#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    #echo $metaf
    MC=$(jq '.change_requested' $metaf)
    if [[ $MC != "null" ]]; then
        echo $metaf $MC
    fi
    #echo $MC
done
