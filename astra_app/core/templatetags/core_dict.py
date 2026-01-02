from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django import template

register = template.Library()


@register.filter(name="dict_get")
def dict_get(mapping: Mapping[str, Any] | None, key: str) -> Any:  # noqa: ANN401
    """Safely get a value from a dict-like object.

    Django templates can raise VariableDoesNotExist when trying to access missing
    keys via dot-lookup inside tags like `{% with %}`. This filter keeps template
    partials resilient across bound/unbound forms.
    """

    if mapping is None:
        return ""
    return mapping.get(key, "")
