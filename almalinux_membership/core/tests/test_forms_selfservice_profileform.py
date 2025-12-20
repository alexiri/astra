from __future__ import annotations

from django.test import SimpleTestCase

from core.forms_selfservice import ProfileForm


class ProfileFormValidationTests(SimpleTestCase):
    def test_github_username_strips_at_and_validates(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasGitHubUsername": "@octocat",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fasGitHubUsername"], "octocat")

    def test_github_username_rejects_invalid(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasGitHubUsername": "-bad-",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fasGitHubUsername", form.errors)

    def test_gitlab_username_strips_at_and_validates(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasGitLabUsername": "@good.name",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fasGitLabUsername"], "good.name")

    def test_chat_nick_accepts_matrix_url_forms_and_keeps_scheme(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasIRCNick": "matrix://matrix.example/alice\nmatrix:/bob",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        # Noggin stores chat nicks as URLs that include the scheme (irc/matrix).
        # This ensures we can render correct links later.
        cleaned = form.cleaned_data["fasIRCNick"].splitlines()
        self.assertIn("matrix://matrix.example/alice", cleaned)
        self.assertIn("matrix:/bob", cleaned)

    def test_timezone_accepts_valid_iana_timezone(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasTimezone": "UTC",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fasTimezone"], "UTC")

    def test_timezone_rejects_invalid_timezone(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasTimezone": "Not/AZone",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fasTimezone", form.errors)

    def test_website_url_requires_http_or_https(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasWebsiteUrl": "ftp://example.org",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fasWebsiteUrl", form.errors)

    def test_website_url_accepts_multiple_lines_and_commas(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasWebsiteUrl": "https://example.org, https://example.com\nhttps://example.net",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_irc_nick_accepts_nick_and_nick_server(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasIRCNick": "nick\nnick:irc.example.org",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_irc_nick_accepts_irc_url_forms(self):
        form = ProfileForm(
            data={
                "givenname": "Alice",
                "sn": "User",
                "fasIRCNick": "irc://irc.example.org/nick",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["fasIRCNick"].strip(), "irc://irc.example.org/nick")
