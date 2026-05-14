#!/bin/sh
set -e

echo "Running database migrations..."
alembic -c migrations/alembic.ini upgrade head

echo "Starting admin-service..."
exec "$@"
