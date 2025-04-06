#!/usr/bin/sh

curl -H 'X-Refresh-Token: '$1 http://subwaive:8000/$2/refresh/by-token/