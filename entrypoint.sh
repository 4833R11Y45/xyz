#!/bin/sh
set -e
service ssh start
exec gunicorn --bind=0.0.0.0:80 --timeout 3000 --workers=4 app:app