from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

from core import views_groups, views_settings, views_users
from core.agreements import AgreementForUser
from core.backends import FreeIPAOperationFailed


class GroupsSponsorsAndAgreementsTests(TestCase):
    def _add_session_and_messages(self, request):
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def _auth_user(self, username: str):
        return SimpleNamespace(is_authenticated=True, get_username=lambda: username, username=username)

    def test_profile_does_not_show_disabled_signed_agreements(self):
        fu = SimpleNamespace(
            username="alice",
            is_authenticated=True,
            get_username=lambda: "alice",
            groups_list=["some-group"],
            _user_data={},
            email="a@example.org",
            get_full_name=lambda: "Alice User",
        )

        disabled = SimpleNamespace(cn="disabled-agreement", enabled=False, users=["alice"], groups=[])
        enabled_other = SimpleNamespace(cn="enabled-agreement", enabled=True, users=[], groups=[])

        with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[]):
            with patch("core.agreements.FreeIPAFASAgreement.all", autospec=True, return_value=[disabled, enabled_other]):
                with patch(
                    "core.agreements.FreeIPAFASAgreement.get",
                    autospec=True,
                    side_effect=lambda cn: disabled if cn == "disabled-agreement" else enabled_other,
                ):
                    ctx = views_users._profile_context_for_user(
                        request=SimpleNamespace(),
                        fu=fu,
                        is_self=True,
                    )

        self.assertEqual(ctx["agreements"], [])
        self.assertEqual(ctx["agreements_count"], 0)

    def test_settings_agreement_detail_disabled_is_not_visible(self):
        factory = RequestFactory()
        request = factory.get("/settings/agreements/disabled-agreement/")
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        disabled = SimpleNamespace(cn="disabled-agreement", enabled=False, users=["alice"], groups=[])

        with patch("core.views_settings.has_enabled_agreements", autospec=True, return_value=True):
            with patch(
                "core.views_settings._get_full_user",
                autospec=True,
                return_value=SimpleNamespace(groups_list=[]),
            ):
                with patch("core.views_settings.FreeIPAFASAgreement.get", autospec=True, return_value=disabled):
                    with self.assertRaises(Http404):
                        views_settings.settings_agreement_detail(request, "disabled-agreement")

    def test_group_detail_leave_group_removes_self(self):
        factory = RequestFactory()
        request = factory.post("/groups/testgroup/", data={"action": "leave"})
        self._add_session_and_messages(request)

        user = self._auth_user("alice")
        user.remove_from_group = MagicMock()
        request.user = user

        group = SimpleNamespace(cn="testgroup", fas_group=True, members=["alice"], sponsors=[])

        with patch("core.views_groups.FreeIPAGroup.get", autospec=True, return_value=group):
            response = views_groups.group_detail(request, "testgroup")

        self.assertEqual(response.status_code, 302)
        user.remove_from_group.assert_called_once_with("testgroup")

    def test_group_detail_sponsor_cannot_add_member_without_signed_agreement(self):
        factory = RequestFactory()
        request = factory.post(
            "/groups/testgroup/",
            data={"action": "add_member", "username": "bob"},
        )
        self._add_session_and_messages(request)

        sponsor_user = self._auth_user("sponsor")
        request.user = sponsor_user

        group_backend = SimpleNamespace(
            cn="testgroup",
            fas_group=True,
            members=[],
            sponsors=["sponsor"],
            add_member=MagicMock(),
        )

        with patch("core.views_groups.FreeIPAGroup.get", autospec=True, return_value=group_backend):
            with patch("core.agreements.FreeIPAFASAgreement.all", autospec=True) as mocked_all:
                mocked_all.return_value = [SimpleNamespace(cn="agree1", enabled=True, groups=["testgroup"], users=[])]
                with patch("core.agreements.FreeIPAFASAgreement.get", autospec=True) as mocked_get:
                    mocked_get.return_value = SimpleNamespace(cn="agree1", enabled=True, groups=["testgroup"], users=[])

                    response = views_groups.group_detail(request, "testgroup")

        self.assertEqual(response.status_code, 302)
        group_backend.add_member.assert_not_called()
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("must sign" in m.lower() for m in msgs), msgs)

    def test_group_detail_add_member_surfaces_freeipa_error_message(self):
        factory = RequestFactory()
        request = factory.post(
            "/groups/testgroup/",
            data={"action": "add_member", "username": "jim"},
        )
        self._add_session_and_messages(request)
        request.user = self._auth_user("sponsor")

        group_backend = SimpleNamespace(
            cn="testgroup",
            fas_group=True,
            members=[],
            sponsors=["sponsor"],
        )

        err = FreeIPAOperationFailed(
            "FreeIPA group_add_member failed (group=testgroup user=jim): member/user: missing user agreement: test"
        )

        with patch("core.views_groups.FreeIPAGroup.get", autospec=True, return_value=group_backend):
            with patch("core.views_groups.missing_required_agreements_for_user_in_group", autospec=True, return_value=[]):
                group_backend.add_member = MagicMock(side_effect=err)
                response = views_groups.group_detail(request, "testgroup")

        self.assertEqual(response.status_code, 302)
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("missing user agreement" in m.lower() for m in msgs), msgs)

    def test_group_detail_sponsor_can_stop_being_sponsor(self):
        factory = RequestFactory()
        request = factory.post(
            "/groups/testgroup/",
            data={"action": "stop_sponsoring"},
        )
        self._add_session_and_messages(request)

        sponsor_user = self._auth_user("sponsor")
        request.user = sponsor_user

        group_backend = SimpleNamespace(
            cn="testgroup",
            fas_group=True,
            members=[],
            sponsors=["sponsor"],
            remove_sponsor=MagicMock(),
        )

        with patch("core.views_groups.FreeIPAGroup.get", autospec=True, return_value=group_backend):
            response = views_groups.group_detail(request, "testgroup")

        self.assertEqual(response.status_code, 302)
        group_backend.remove_sponsor.assert_called_once_with("sponsor")
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("sponsor" in m.lower() for m in msgs), msgs)

    def test_group_detail_renders_sponsors_section_before_members(self):
        factory = RequestFactory()
        request = factory.get("/groups/testgroup/")
        self._add_session_and_messages(request)
        request.user = self._auth_user("alice")

        group = SimpleNamespace(
            cn="testgroup",
            fas_group=True,
            description="Test Group",
            members=["member1"],
            sponsors=["sponsor1"],
            fas_url=None,
            fas_mailing_list=None,
            fas_irc_channels=None,
            fas_discussion_url=None,
        )

        with patch("core.views_groups.FreeIPAGroup.get", autospec=True, return_value=group):
            with patch("core.templatetags.core_user_widget.FreeIPAUser.get", autospec=True, return_value=None):
                response = views_groups.group_detail(request, "testgroup")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Sponsors", html)
        self.assertIn(">sponsor1</a>", html)

        sponsors_pos = html.find("Sponsors")
        members_pos = html.find("Members")
        self.assertNotEqual(sponsors_pos, -1)
        self.assertNotEqual(members_pos, -1)
        self.assertLess(sponsors_pos, members_pos)

    def test_profile_groups_include_role_with_sponsor_precedence(self):
        fu = SimpleNamespace(
            username="alice",
            is_authenticated=True,
            get_username=lambda: "alice",
            groups_list=["g1", "g2"],
            _user_data={},
            email="a@example.org",
            get_full_name=lambda: "Alice User",
        )

        g1 = SimpleNamespace(cn="g1", fas_group=True, members=["alice"], sponsors=[])
        g2 = SimpleNamespace(cn="g2", fas_group=True, members=["alice"], sponsors=["alice"])

        with patch("core.views_users.FreeIPAGroup.all", autospec=True, return_value=[g1, g2]):
            with patch("core.views_users.has_enabled_agreements", autospec=True, return_value=False):
                ctx = views_users._profile_context_for_user(
                    request=SimpleNamespace(),
                    fu=fu,
                    is_self=True,
                )

        groups = ctx["groups"]
        self.assertEqual([g["cn"] for g in groups], ["g1", "g2"])
        roles = {g["cn"]: g["role"] for g in groups}
        self.assertEqual(roles["g1"], "Member")
        self.assertEqual(roles["g2"], "Sponsor")
