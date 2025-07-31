#!/usr/bin/sh

echo "Thinning logs"
curl -s -H 'X-Refresh-Token: '$1 http://subwaive:8000/logs/thin-by-token/