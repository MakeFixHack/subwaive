#!/usr/bin/sh

echo "Refreshing $2"
curl -s -H 'X-Refresh-Token: '$1 http://subwaive:8000/$2/refresh/by-token/