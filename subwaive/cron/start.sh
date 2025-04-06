#!/usr/bin/sh

printenv > /etc/environment
# tail -f /var/log/cron.log &
cron -f