#!/bin/sh
python3 manage.py privileges

gunicorn subwaive.wsgi --bind=0.0.0.0:8000
