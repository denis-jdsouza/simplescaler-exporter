#!/usr/bin/env python3.6
import argparse
import sys
import time
import logging
import os
import signal
import defs
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from prometheus_client import start_http_server, Gauge, REGISTRY

RUNNING = True

# Retrive env variables
UPDATE_PERIOD = int(os.getenv('UPDATE_PERIOD', 15))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(format='%(levelname)s: %(message)s', level=LOG_LEVEL)
logging.debug(f'UPDATE_PERIOD value is: {UPDATE_PERIOD}')
logging.debug(f'LOG_LEVEL value is: {LOG_LEVEL}')

def unregister_default_metrics():
    """ Function to unregister all default metrics exposed by 'prometheus_client' library """
    for name in list(REGISTRY._names_to_collectors.values()):
        try:
            REGISTRY.unregister(name)
        except KeyError:
            pass
    logging.debug("cleared unwanted/stale metrics...")

def define_metrics():
    """ Function to define metrics exposed by exporter in Prometehus format """
    MIN_REPLICAS = Gauge('kube_simplescaler_spec_min_replicas','Minimum number of replicas',['scaler', 'namespace', 'target'])
    MAX_REPLICAS = Gauge('kube_simplescaler_spec_max_replicas','Maximum number of replicas',['scaler', 'namespace', 'target'])
    COOL_DOWN_PERIOD = Gauge('kube_simplescaler_spec_cool_down_period_seconds','Cooldown period after scaleup/scaledown',['scaler', 'namespace', 'target'])
    EVALUATIONS = Gauge('kube_simplescaler_spec_evaluations','Number of evaluations before scaling happens',['scaler', 'namespace', 'target'])
    SCALE_DOWN = Gauge('kube_simplescaler_spec_scale_down','Scale Down threshold in CPU utilization percentage',['scaler', 'namespace', 'target'])
    SCALE_UP = Gauge('kube_simplescaler_spec_scale_up','Scale Up threshold in CPU utilization percentage',['scaler', 'namespace', 'target'])
    SCALE_DOWN_SIZE = Gauge('kube_simplescaler_spec_scale_down_size','Number of pods to scale down',['scaler', 'namespace', 'target'])
    SCALE_UP_SIZE = Gauge('kube_simplescaler_spec_scale_up_size','Number of pods to scale up',['scaler', 'namespace', 'target'])
    return MIN_REPLICAS, MAX_REPLICAS, COOL_DOWN_PERIOD, EVALUATIONS, SCALE_DOWN, SCALE_UP, SCALE_DOWN_SIZE, SCALE_UP_SIZE

def gather_metrics():
    """ Function to gather required metrics from Kubernets API """
    customsapi = client.CustomObjectsApi()
    try:
        api_response = customsapi.list_cluster_custom_object(defs.CUSTOM_GROUP, defs.CUSTOM_VERSION, defs.CUSTOM_PLURAL)
    except ApiException as e:
        logging.error(f'Exception when calling CRD list_cluster_custom_object, please check if CUSTOM_KIND: {defs.CUSTOM_KIND} exists in the cluster: {e}')
        sys.exit(1)
    return api_response

def handle_sigterm(*args):
    """ Function to implement graceful shutdown when 'SIGTERM/SIGINT' is received """
    global RUNNING
    logging.warning('SIGTERM/SIGINT received stopping exporter...')
    RUNNING = False

def main():
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    # Process arguments passed to load the correct Kubernetes config
    parser = argparse.ArgumentParser()
    parser.add_argument('--kubeconfig', help='path to kubeconfig file, only required if running outside of a cluster')
    args = parser.parse_args()

    if args.kubeconfig is not None:
        LOAD_KUBE_CONFIG = "yes"
        logging.info(f'kubeconfig provided: {args.kubeconfig}')
    else:
        LOAD_KUBE_CONFIG = "no"
        logging.info("kubeconfig not provided, loading incluster config")

    unregister_default_metrics()

    # Start Prometheus exporter web-server
    start_http_server(8000)
    logging.info('starting simple-scaler prometheus exporter...')

    while RUNNING:
        # Load the required Kuberentes config to connect to cluster
        if LOAD_KUBE_CONFIG == "yes":
            config.load_kube_config(config_file=args.kubeconfig, persist_config=False)
        else:
            config.load_incluster_config()

        # Process metrics gathered from Kubernets API response
        api_response = gather_metrics()

        # Unregister previous stale metrics
        unregister_default_metrics()
        MIN_REPLICAS, MAX_REPLICAS, COOL_DOWN_PERIOD, EVALUATIONS, SCALE_DOWN, SCALE_UP, SCALE_DOWN_SIZE, SCALE_UP_SIZE = define_metrics()

        if not api_response.get("items"):
            logging.info(f'no objects found for Custom Resource: {defs.CUSTOM_KIND}')
        for scaler in api_response.get("items"):
            MIN_REPLICAS.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['minReplicas'])
            MAX_REPLICAS.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['maxReplicas'])
            COOL_DOWN_PERIOD.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['coolDownPeriod'])
            EVALUATIONS.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['evaluations'])
            SCALE_DOWN.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['scaleDown'])
            SCALE_UP.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['scaleUp'])
            SCALE_DOWN_SIZE.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['scaleDownSize'])
            SCALE_UP_SIZE.labels(scaler['metadata']['name'], scaler['metadata']['namespace'], scaler['spec']['target']['name']).set(scaler['spec']['scaleUpSize'])

            logging.info(f"Processing metrics for {defs.CUSTOM_KIND}: {scaler['metadata']['name']} in namespace: {scaler['metadata']['namespace']}")
        time.sleep(UPDATE_PERIOD)

if __name__ == '__main__':
    main()