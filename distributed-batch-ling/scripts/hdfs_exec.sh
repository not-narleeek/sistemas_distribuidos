#!/bin/sh
set -eu

HDFS_BIN=""

if command -v hdfs >/dev/null 2>&1; then
    HDFS_BIN="$(command -v hdfs)"
else
    for candidate in /opt/hadoop/bin/hdfs /opt/hadoop-3.2.1/bin/hdfs; do
        if [ -x "$candidate" ]; then
            HDFS_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "${HDFS_BIN}" ]; then
    echo >&2 "Unable to locate hdfs binary"
    exit 127
fi

exec "$HDFS_BIN" "$@"
