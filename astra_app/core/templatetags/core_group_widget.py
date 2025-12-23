from __future__ import annotations

from typing import Any, cast

from django.template import Context, Library
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from core.backends import FreeIPAGroup
from core.views_utils import _normalize_str

register = Library()


@register.simple_tag(takes_context=True, name="group")
def group_widget(context: Context, group: object, **kwargs: Any) -> str:
    raw = _normalize_str(group)
    if not raw:
        return ""

    extra_class = kwargs.get("class", "") or ""
    extra_style = kwargs.get("style", "") or ""

    render_cache = context.render_context

    existing_obj_cache = render_cache.get("_core_group_widget_cache")
    if not isinstance(existing_obj_cache, dict):
        existing_obj_cache = {}
        render_cache["_core_group_widget_cache"] = existing_obj_cache
    obj_cache = cast(dict[str, object | None], existing_obj_cache)

    existing_count_cache = render_cache.get("_core_group_widget_count_cache")
    if not isinstance(existing_count_cache, dict):
        existing_count_cache = {}
        render_cache["_core_group_widget_count_cache"] = existing_count_cache
    count_cache = cast(dict[str, int], existing_count_cache)

    group_obj = obj_cache.get(raw)
    if group_obj is None:
        group_obj = FreeIPAGroup.get(raw)
        obj_cache[raw] = group_obj

    def _get_list_attr(obj: object, name: str) -> list[str]:
        # Template tag accepts duck-typed objects (e.g. tests pass SimpleNamespace).
        value = getattr(obj, name, None)
        if not value:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _recursive_usernames(cn: str, *, visited: set[str]) -> set[str]:
        key = cn.strip().lower()
        if not key or key in visited:
            return set()
        visited.add(key)

        obj = obj_cache.get(cn)
        if obj is None:
            obj = FreeIPAGroup.get(cn)
            obj_cache[cn] = obj
        if obj is None:
            return set()

        users: set[str] = set(_get_list_attr(obj, "members"))
        for child_cn in sorted(set(_get_list_attr(obj, "member_groups")), key=str.lower):
            users |= _recursive_usernames(child_cn, visited=visited)
        return users

    member_count = count_cache.get(raw)
    if member_count is None:
        member_count = 0
        if group_obj is not None:
            member_count = len(_recursive_usernames(raw, visited=set()))
        count_cache[raw] = member_count

    description = ""
    if group_obj is not None:
        desc = getattr(group_obj, "description", "")
        if isinstance(desc, str):
            description = desc.strip()

    html = render_to_string(
        "core/_group_widget.html",
        {
            "cn": raw,
            "member_count": member_count,
            "description": description,
            "extra_class": extra_class,
            "extra_style": extra_style,
        },
        request=context.get("request"),
    )
    return mark_safe(html)
