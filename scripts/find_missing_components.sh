#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    #echo $metaf
    MC=$(jq '.labels' $metaf)
    if [[ $MC != *"c:"* ]] && [[ $MC != *"module"* ]]; then

        NUMBER=$(echo $metaf | cut -d\/ -f9)
        #echo $NUMBER

        # check the last known state
        STATE=$(jq '.www_summary.state' $metaf) 
        if [[ $STATE == "\"open\"" ]]; then

            ITYPE=$(jq '.www_summary.type' $metaf)
            echo $ITYPE
            if [[ $ITYPE != "\"pullrequest\"" ]]; then
                echo $NUMBER
            fi
        fi

        #exit 1
    fi

done
