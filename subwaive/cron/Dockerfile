ARG PYTHON_VERSION=3.11.9
FROM python:${PYTHON_VERSION}-slim AS base

# install cron
RUN apt-get update && apt-get -y install cron
RUN apt-get update && apt-get -y install curl
# RUN apt-get update && apt-get -y install procps

WORKDIR /app
COPY data_refresh.sh /app/
RUN chmod 0644 /app/data_refresh.sh

COPY crontab /etc/cron.d/crontab
RUN chmod 0644 /etc/cron.d/crontab
RUN crontab /etc/cron.d/crontab
RUN touch /var/log/cron.log

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

ENTRYPOINT ["/app/start.sh"]
