import jinja2
from enum import Enum


class PodType(Enum):
    NORMAL     = 1
    SRIOV      = 2
    HOSTBACKED = 3


def j2_render(in_file_name, out_file_name, kwargs):
    with open(in_file_name) as inFile:
        contents = inFile.read()
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)
