FROM alpine:3.15

RUN apk add --no-cache \
      python3 py3-pip py3-setuptools py3-wheel \
      py3-virtualenv \
      py3-aiohttp \
      py3-magic \
      py3-ruamel.yaml \
      py3-commonmark \
      su-exec

COPY requirements.txt /opt/acd-appservice/requirements.txt
WORKDIR /opt/acd-appservice
RUN apk add --virtual .build-deps python3-dev libffi-dev build-base \
 && pip3 install -r requirements.txt \
 && apk del .build-deps

COPY . /opt/acd-appservice
RUN cp acd_appservice/example-config.yaml .
VOLUME /data

CMD ["/opt/acd-appservice/docker-run.sh"]
