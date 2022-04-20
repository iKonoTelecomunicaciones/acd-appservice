#!/bin/sh
cd /opt/acd-appservice


if [ ! -f config.yaml ]; then
	cp example-config.yaml config.yaml
	echo "Didn't find a config file."
	echo "Copied default config file to config.yaml"
	echo "Modify that config file to your liking."
	echo "Start the container again after that to generate the registration file."
	exit
fi

if [ ! -f registration.yaml ]; then
	python3 -m acd_appservice -g -c config.yaml -r registration.yaml
	exit
fi

exec python3 -m acd_appservice -c config.yaml
