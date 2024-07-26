import jinja2

from typing import Any


def j2_render_data(contents: str, kwargs: dict[str, Any]) -> str:
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    return rendered


def j2_render(in_file_name: str, out_file_name: str, kwargs: dict[str, Any]) -> str:
    with open(in_file_name) as inFile:
        contents = inFile.read()
    rendered = j2_render_data(contents, kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)
    return rendered
