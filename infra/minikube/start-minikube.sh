#!/bin/bash
minikube start -p supply-chain-demo --cpus=4 --memory=8192 --driver=docker
echo "Minikube started with 4 CPUs and 8GB RAM."