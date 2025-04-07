#!/bin/bash 

_term() { 
  echo "Caught SIGTERM signal!" 
  kill -TERM "$child" 2>/dev/null
}

trap _term SIGTERM

printenv > /etc/environment
echo "starting cron"
cron -f &

child=$! 
wait "$child"