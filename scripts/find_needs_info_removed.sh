#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    #echo $metaf
    REMOVED=$(jq '.actions.unlabel' $metaf)
    if [[ $REMOVED == *"needs_info"* ]]; then
        echo $metaf
    fi
done
