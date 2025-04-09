FROM alpine:3.7

RUN apk --no-cache add curl

COPY crontab /tmp/crontab
RUN cat /tmp/crontab > /etc/crontabs/root
COPY data_refresh.sh /tmp/

ENTRYPOINT ["crond", "-f"]