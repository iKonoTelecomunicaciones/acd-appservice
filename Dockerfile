FROM alpine:3.17

RUN apk add --no-cache \
      python3 py3-pip py3-setuptools py3-wheel \
      py3-pillow \
      py3-aiohttp \
      py3-magic \
      py3-ruamel.yaml \
      py3-commonmark \
      su-exec

COPY requirements.txt /opt/acd-appservice/requirements.txt
WORKDIR /opt/acd-appservice
RUN apk add --virtual .build-deps python3-dev libffi-dev build-base \
      && pip3 install --no-cache-dir -r requirements.txt \
      && apk del .build-deps

COPY . /opt/acd-appservice
RUN apk add --no-cache git \
      && python3 setup.py --version \
      && pip3 install .[all] \
      && cp acd_appservice/example-config.yaml . \
      && rm -rf acd_appservice .git build
VOLUME /data

CMD ["/opt/acd-appservice/docker-run.sh"]
