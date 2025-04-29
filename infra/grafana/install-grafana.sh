#!/bin/bash
# Add Helm repo and install Grafana
helm install loki grafana/loki-stack --set promtail.enabled=false

kubectl port-forward service/loki-grafana 3000:80