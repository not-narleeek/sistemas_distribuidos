#!/bin/bash
set -e

echo "Waiting for MongoDB to be ready..."
until mongosh --host "$MONGO_INITDB_HOST" --port "$MONGO_INITDB_PORT" --eval "db.adminCommand({ ping: 1 })" >/dev/null 2>&1; do
    echo "MongoDB is not ready yet..."
    sleep 1
done

echo "MongoDB is up, checking if collection exists..."

COLLECTION_EXISTS=$(mongosh --quiet --host "$MONGO_INITDB_HOST" --port "$MONGO_INITDB_PORT" \
    --eval "db.getSiblingDB('$MONGO_INITDB_DATABASE').getCollectionNames().includes('$MONGO_INITDB_COLLECTION')")

if [ "$COLLECTION_EXISTS" = "true" ]; then
    echo "Collection '$MONGO_INITDB_COLLECTION' already exists. Skipping import."
else
    echo "Collection '$MONGO_INITDB_COLLECTION' does not exist. Importing data..."
    mongoimport \
        --host "$MONGO_INITDB_HOST" \
        --port "$MONGO_INITDB_PORT" \
        --db "$MONGO_INITDB_DATABASE" \
        --collection "$MONGO_INITDB_COLLECTION" \
        --file /bdd.json
    echo "Import complete."
fi
