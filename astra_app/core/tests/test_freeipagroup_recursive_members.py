from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from core.backends import FreeIPAGroup


class FreeIPAGroupRecursiveMembersTests(TestCase):
    def test_recursive_member_count_includes_nested_groups_and_dedupes(self) -> None:
        parent = FreeIPAGroup(
            "parent",
            {
                "cn": ["parent"],
                "member_user": ["alice"],
                "member_group": ["child"],
                "objectclass": ["fasgroup"],
            },
        )
        child = FreeIPAGroup(
            "child",
            {
                "cn": ["child"],
                "member_user": ["alice", "bob"],
                "member_group": ["grand"],
                "objectclass": ["fasgroup"],
            },
        )
        grand = FreeIPAGroup(
            "grand",
            {
                "cn": ["grand"],
                "member_user": ["carol"],
                "member_group": [],
                "objectclass": ["fasgroup"],
            },
        )

        def _fake_get(cn: str):
            return {"parent": parent, "child": child, "grand": grand}.get(cn)

        with patch("core.backends.FreeIPAGroup.get", side_effect=_fake_get):
            usernames = parent.member_usernames_recursive()

        self.assertEqual(usernames, {"alice", "bob", "carol"})
        self.assertEqual(parent.member_count_recursive(), 3)
