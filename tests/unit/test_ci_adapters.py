"""
title: Unit — CI adapter templates accept only bare allowed fields
summary: Both configured templates refuse malformed or executable format syntax with a named repair and no configured text; shipped templates and literal braces keep their rendering.
"""

from pathlib import Path
from typing import Any

import config_loader
import pytest

import ci_adapters

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_KEYS = ["marker", "gitlab_image"]
_REFUSED = [
    ("{0}", "positional"),
    ("{}", "positional"),
    ("{unknown}", "unknown field"),
    ("{", "malformed braces"),
    ("}", "malformed braces"),
    ("{FIELD!r}", "conversion"),
    ("{FIELD!s}", "conversion"),
    ("{FIELD!a}", "conversion"),
    ("{FIELD:>20}", "format spec"),
    ("{FIELD:}", "format spec"),
    ("{FIELD:{unknown}}", "format spec"),
    ("{FIELD.__class__}", "attribute"),
    ("{FIELD[0]}", "index"),
]


@pytest.fixture
def pipeline_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config = config_loader.read(str(_ROOT))
    monkeypatch.setattr(config_loader, "read", lambda root: config)
    return config


def _render(key: str) -> str:
    if key == "marker":
        return ci_adapters.marker(_ROOT, "github")
    image: str = ci_adapters.gitlab_document(_ROOT)["test"]["image"]
    return image


@pytest.mark.parametrize("key", _KEYS)
@pytest.mark.parametrize("form, cause", _REFUSED)
def test_configured_template_refuses_unsafe_fields_with_repair(
    pipeline_config: dict[str, Any], key: str, form: str, cause: str
) -> None:
    field = "adapter" if key == "marker" else "python"
    pipeline_config["ci_pipeline"][key] = form.replace("FIELD", field)
    with pytest.raises(AssertionError) as refused:
        _render(key)
    message = str(refused.value)
    assert "ci_pipeline." + key in message
    assert cause in message
    assert "allowed fields:" in message
    allowed = (
        {"adapter"} if key == "marker" else {"python", "node_major", "runner_images"}
    )
    for name in allowed:
        assert name in message
    assert "repair" in message
    assert "bare named fields" in message


@pytest.mark.parametrize("key", _KEYS)
def test_refusal_omits_configured_text(
    pipeline_config: dict[str, Any], key: str
) -> None:
    secret = "private-template-value"
    template = secret + "{private_field}"
    pipeline_config["ci_pipeline"][key] = template
    with pytest.raises(AssertionError) as refused:
        _render(key)
    message = str(refused.value)
    assert template not in message
    assert secret not in message
    assert "private_field" not in message


def test_shipped_values_render_unchanged(pipeline_config: dict[str, Any]) -> None:
    assert ci_adapters.marker(_ROOT, "github") == "# keel-adapter: github"
    assert ci_adapters.marker(_ROOT, "gitlab") == "# keel-adapter: gitlab"
    toolchain = pipeline_config["toolchain"]
    assert _render("gitlab_image") == "ci-image.example.invalid/python%s-node%s" % (
        toolchain["python"],
        toolchain["node_major"],
    )


@pytest.mark.parametrize("key", _KEYS)
@pytest.mark.parametrize("template", ["literal", "{{literal:}}", "{{{FIELD}}}:{FIELD}"])
def test_literals_escaped_braces_and_repeated_fields_render(
    pipeline_config: dict[str, Any], key: str, template: str
) -> None:
    field = "adapter" if key == "marker" else "python"
    value = "github" if key == "marker" else pipeline_config["toolchain"]["python"]
    template = template.replace("FIELD", field)
    pipeline_config["ci_pipeline"][key] = template
    assert _render(key) == template.format(**{field: value})
