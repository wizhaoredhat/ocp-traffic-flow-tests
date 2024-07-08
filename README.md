# Traffic Flow Test Scripts

This repository contains the yaml files, docker files, and test scripts to test Traffic Flows in an OVN-Kubernetes k8s cluster.

## Setting up the environment

The package "kubectl" should be installed.

The recommended python version is 3.11 for running the Traffic Flow tests

```
python -m venv tft-venv
source tft-venv/bin/activate
pip3 install --upgrade pip
pip3 install -r requirements.txt
```

## Configuration YAML fields:

```
tft:
  - name: "(1)"
    namespace: "(2)"
    # test cases can be specified individually i.e "1,2,POD_TO_HOST_SAME_NODE,6" or as a range i.e. "POD_TO_POD_SAME_NODE-9,15-19"
    test_cases: "(3)"
    duration: "(4)"
    # Location of artifacts from run can be specified: default <working-dir>/ft-logs/
    # logs: "/tmp/ft-logs"
    connections:
      - name: "(5)"
        type: "(6)"
        instances: (7)
        server:
          - name: "(8)"
            persistent: "(9)"
            sriov: "(10)"
            default-network: "(11)"
        client:
          - name: "(12)"
            sriov: "(13)"
            default-network: "(14)"
        plugins:
          - name: (15)
          - name: (15)
```

1. "name" - This is the name of the test. Any string value to identify the test.
2. "namespace" - The k8s namespace where the test pods will be run on
3. "test_cases" - A list of the tests that can be run. This can be either a string
     that possibly contains ranges (comma separated, ranged separated by '-'), or a
     YAML list.
    | ID | Test Name            |
    | -- | -------------------- |
    | 1  | POD_TO_POD_SAME_NODE |
    | 2  | POD_TO_POD_DIFF_NODE |
    | 3  | POD_TO_HOST_SAME_NODE |
    | 4  | POD_TO_HOST_DIFF_NODE |
    | 5  | POD_TO_CLUSTER_IP_TO_POD_SAME_NODE |
    | 6  | POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE |
    | 7  | POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE |
    | 8  | POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE |
    | 9  | POD_TO_NODE_PORT_TO_POD_SAME_NODE |
    | 10 | POD_TO_NODE_PORT_TO_POD_DIFF_NODE |
    | 11 | POD_TO_NODE_PORT_TO_HOST_SAME_NODE |
    | 12 | POD_TO_NODE_PORT_TO_HOST_DIFF_NODE |
    | 13 | HOST_TO_HOST_SAME_NODE |
    | 14 | HOST_TO_HOST_DIFF_NODE |
    | 15 | HOST_TO_POD_SAME_NODE |
    | 16 | HOST_TO_POD_DIFF_NODE |
    | 17 | HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE |
    | 18 | HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE |
    | 19 | HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE |
    | 20 | HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE |
    | 21 | HOST_TO_NODE_PORT_TO_POD_SAME_NODE |
    | 22 | HOST_TO_NODE_PORT_TO_POD_DIFF_NODE |
    | 23 | HOST_TO_NODE_PORT_TO_HOST_SAME_NODE |
    | 24 | HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE |
    | 25 | POD_TO_EXTERNAL |
    | 26 | HOST_TO_EXTERNAL |
4. "duration" - The duration that each individual test will run for.
5. "name" - This is the connection name. Any string value to identify the connection.
6. "type" - Supported types of connections are iperf-tcp, iperf-udp, netperf-tcp-stream, netperf-tcp-rr
7. "instances" - The number of instances that would be created. Default is "1"
8. "name" - The node name of the server.
9. "persistent" - Whether to have the server pod persist after the test. Takes in "true/false"
10. "sriov" - Whether SRIOV should be used for the server pod. Takes in "true/false"
11. "default-network" - (Optional) The name of the default network that the sriov pod would use.
12. "name" - The node name of the client.
13. "sriov" - Whether SRIOV should be used for the client pod. Takes in "true/false"
14. "default-network" - (Optional) The name of the default network that the sriov pod would use.
15. "name" - (Optional) list of plugin names
    | Name             | Description          |
    | ---------------- | -------------------- |
    | measure_cpu      | Measure CPU Usage    |
    | measure_power    | Measure Power Usage  |
    | validate_offload | Verify OvS Offload   |

## Running the tests

Simply run the python application as so:

```
python main.py config.yaml
```

## Environment variables

- `TFT_TEST_IMAGE` specify the test image. Defaults to `quay.io/wizhao/tft-tools:latest`.
     This is mainly for development and manual testing, to inject another container image.
- `TFT_IMAGE_PULL_POLICY` the image pull policy. One of `IfNotPresent`, `Always`, `Never`.
     Defaults to `IfNotPresent`m unless `$TFT_TEST_IMAGE` is set (in which case it defaults
     to `Always`).
