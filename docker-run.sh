#!/bin/sh

# Check if the config file exists
if [ ! -f /data/config.yaml ]; then
	cp example-config.yaml /data/config.yaml
	echo "Didn't find a config file."
	echo "Copied default config file to /data/config.yaml"
	echo "Modify that config file to your liking."
	echo "Start the container again after that to generate the registration file."
	exit
fi

# Check if the registration file exists
if [ ! -f /data/registration.yaml ]; then
	python3 -m acd_appservice -g -c /data/config.yaml -r /data/registration.yaml
	echo "Didn't find a registration file."
	echo "Copied default registration file to /data/registration.yaml"
	echo "Modify that registration file to your liking."
	exit
fi

# Components.yaml file path
source_components_yaml="acd_appservice/web/api/components.yaml"

# Check if the components.yaml file is not exists and copy it from the repo
if [ -e "${source_components_yaml}" ] && [ ! -e "components.yaml" ]; then
	cp -vf ${source_components_yaml} components.yaml
	echo "Copied ./components.yaml file from acd_appservice/web/api/"
fi

# Check if the components.yaml file exists and is different from the source file
if [ -e "${source_components_yaml}" ] && [ -e "components.yaml" ]; then
	if [ -n "$(diff ${source_components_yaml} components.yaml)" ]; then
		cp -vf ${source_components_yaml} components.yaml
		echo "Updated ./components.yaml file"
	fi
fi

if [ "$1" = "dev" ]; then
	# Install requirements for development
	pip install -r requirements-dev.txt
	# Configure git to use the safe directory
	if ! [ $(git config --global --get safe.directory) ]; then
		echo "Setting safe.directory config to /opt/acd-appservice"
		git config --global --add safe.directory /opt/acd-appservice
	fi
	# Getting the version from git repository
	python3 setup.py --version
	# Run the app
  watchmedo auto-restart --recursive --pattern="*.py" --directory="." /opt/acd-appservice/docker-run.sh
fi

exec python3 -m acd_appservice -c /data/config.yaml
