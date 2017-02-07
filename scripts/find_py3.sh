#!/bin/bash

IPATH=/home/jtanner/.ansibullbot/cache/ansible/ansible/issues

for metaf in $(find $IPATH -type f -name "meta.json"); do
    fgrep -i -e 'python3' -e 'python 3' -e 'py3' $metaf | fgrep -v 'is_py3' 1>/dev/null
    RC=$?
    if [[ $RC == 0 ]]; then
        echo $metaf
    fi
done
