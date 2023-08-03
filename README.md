# Openshift Traffic Flow Test Scripts

This repository contains the yaml files, docker files, and test scripts to test Traffic Flows in an OVN-Kubernetes cluster.

## Setting up the environment

```
python -m venv tft-venv
source tft-venv/bin/activate
pip3 install --upgrade pip
pip3 install -r requirements.txt
```

## Creating the docker pods

```
sudo podman build -t quay.io/wizhao/tft-tools:0.1-x86_64 -f ./Containerfile .
sudo podman push quay.io/wizhao/tft-tools:0.1-x86_64
sudo podman build --platform linux/arm64 -t quay.io/wizhao/tft-tools:0.1-aarch64 -f ./Containerfile .
sudo podman push quay.io/wizhao/tft-tools:0.1-aarch64
sudo podman manifest create tft-tools-0.1-list
sudo podman manifest add tft-tools-0.1-list quay.io/wizhao/tft-tools:0.1-x86_64
sudo podman manifest add tft-tools-0.1-list quay.io/wizhao/tft-tools:0.1-aarch64
sudo podman manifest push tft-tools-0.1-list quay.io/wizhao/tft-tools:0.1
```

