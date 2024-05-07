#!/bin/bash

# Helper script to print results in consice human-friendly way. Return an error code in the event any failure is detected.

print_details() {
    jq '. | "Test ID: \(.test_id), Test Type: \(.test_type), Reverse: \(.reverse), TX Bitrate: \(.bitrate_gbps.tx) Gbps, RX Bitrate: \(.bitrate_gbps.rx) Gbps"'
}

if [ "$#" -eq 0 ]; then
    echo "No JSON file specified. Usage: $0 <RESULTS.json file>"
    exit 1
else
    JSON_FILE="$1"
fi

SUCCESS_COUNT=$(jq '.passing | length' $JSON_FILE)

if [ "$SUCCESS_COUNT" -gt 0 ]; then
    echo "There are $SUCCESS_COUNT passing flows. Details:"
    jq -c '.passing[]' $JSON_FILE | while read item; do
	echo "$item" | print_details
    done
    echo -e "\n\n\n"
fi


FAIL_COUNT=$(jq '.failing | length' $JSON_FILE)

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "There are $FAIL_COUNT failing flows. Details:"
    jq -c '.failing[]' $JSON_FILE | while read item; do
        echo "$item" | print_details
    done
    exit 1
else
    echo "No failures detected in results"
fi

