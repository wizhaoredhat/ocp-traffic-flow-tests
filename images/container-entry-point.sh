#!/bin/bash

if [ "$#" -eq 0 ] ; then
    ARGS=("/usr/bin/sleep" "infinity")
else
    ARGS=("$@")
fi

exec /usr/bin/tini -p SIGTERM -g -e 143 -- "${ARGS[@]}"
