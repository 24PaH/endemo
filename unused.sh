#!/bin/bash

requirements="requirements.txt"

while read -r line
do
    grep -rinI "$line" endemo2/ > /dev/null
    if (($? == 0)); then
        echo "$line"
    fi
done < "$requirements"

