import jinja2
from enum import Enum


class PodType(Enum):
    NORMAL     = 1
    SRIOV      = 2
    HOSTBACKED = 3

class TestCaseType(Enum):
    POD_TO_POD_SAME_NODE                 = 1
    POD_TO_POD_DIFF_NODE                 = 2
    POD_TO_HOST_SAME_NODE                = 3
    POD_TO_HOST_DIFF_NODE                = 4
    POD_TO_CLUSTER_IP_TO_POD_SAME_NODE   = 5
    POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE   = 6
    POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE  = 7
    POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE  = 8
    POD_TO_NODE_PORT_TO_POD_SAME_NODE    = 9
    POD_TO_NODE_PORT_TO_POD_DIFF_NODE    = 10
    POD_TO_NODE_PORT_TO_HOST_SAME_NODE   = 11
    POD_TO_NODE_PORT_TO_HOST_DIFF_NODE   = 12
    HOST_TO_HOST_SAME_NODE               = 13
    HOST_TO_HOST_DIFF_NODE               = 14
    HOST_TO_POD_SAME_NODE                = 15
    HOST_TO_POD_DIFF_NODE                = 16
    HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE  = 17
    HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE  = 18
    HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE = 19
    HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE = 20
    HOST_TO_NODE_PORT_TO_POD_SAME_NODE   = 21
    HOST_TO_NODE_PORT_TO_POD_DIFF_NODE   = 22
    HOST_TO_NODE_PORT_TO_HOST_SAME_NODE  = 23
    HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE  = 24
    POD_TO_EXTERNAL                      = 25
    HOST_TO_EXTERNAL                     = 26

class ConnectionMode(Enum):
    POD_IP                               = 1
    CLUSTER_IP                           = 2
    NODE_PORT_IP                         = 3
    EXTERNAL_IP                          = 4


def j2_render(in_file_name, out_file_name, kwargs):
    with open(in_file_name) as inFile:
        contents = inFile.read()
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)
