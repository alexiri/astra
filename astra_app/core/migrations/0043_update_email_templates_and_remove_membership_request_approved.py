from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import override

from django.db import migrations


class _TextFromHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignore_depth = 0
        self._anchor_stack: list[tuple[str | None, list[str]]] = []
        self._blockquote_depth = 0
        self._list_depth = 0
        self._verbatim_depth = 0
        self._heading_level: int | None = None

    def _append_text(self, text: str) -> None:
        if not text:
            return

        if self._verbatim_depth:
            cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        else:
            cleaned = re.sub(r"\s+", " ", text)

        if not cleaned.strip() and not self._verbatim_depth:
            return

        if self._heading_level is not None and (not self._parts or self._parts[-1].endswith("\n")):
            self._parts.append("#" * self._heading_level + " ")
        self._heading_level = None

        self._parts.append(cleaned)

    def _endswith_newline(self) -> bool:
        return bool(self._parts) and self._parts[-1].endswith("\n")

    def _ensure_newline(self) -> None:
        if not self._parts:
            return
        if self._endswith_newline():
            return
        self._parts.append("\n")
        if self._blockquote_depth:
            self._parts.append("> ")

    def _ensure_blank_line(self) -> None:
        if not self._parts:
            return
        # Ensure we end with exactly one blank line (two newlines).
        tail = "".join(self._parts[-3:])
        if tail.endswith("\n\n"):
            return
        self._ensure_newline()
        self._ensure_newline()

    @property
    def text(self) -> str:
        raw = "".join(self._parts)
        raw = raw.replace("\xa0", " ")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n[ \t]+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [ln.rstrip() for ln in raw.split("\n")]
        return "\n".join(lines).strip()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return

        tag = tag.lower()

        if tag == "br":
            self._ensure_newline()
            return
        if tag == "hr":
            self._ensure_newline()
            self._parts.append("\n---")
            self._ensure_blank_line()
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._ensure_newline()
            try:
                self._heading_level = max(1, min(6, int(tag[1:])))
            except ValueError:
                self._heading_level = 3
            return

        if tag == "blockquote":
            self._ensure_newline()
            self._blockquote_depth += 1
            # Prefix the first line.
            self._parts.append("> ")
            return

        if tag == "li":
            self._ensure_newline()
            self._parts.append("- ")
            return

        if tag in {"ul", "ol"}:
            self._ensure_newline()
            self._list_depth += 1
            return

        if tag in {"p", "div"}:
            self._ensure_newline()
            self._parts.append("\n")
            return

        if tag == "pre":
            self._ensure_newline()
            self._verbatim_depth += 1
            return

        if tag in {"b", "strong"}:
            self._append_text("**")
            return
        if tag in {"i", "em"}:
            self._append_text("*")
            return
        if tag == "u":
            self._append_text("_")
            return
        if tag == "a":
            href: str | None = None
            for k, v in attrs:
                if k == "href" and v:
                    href = v
                    break
            self._anchor_stack.append((href, []))

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return

        tag = tag.lower()

        if tag in {"b", "strong"}:
            self._append_text("**")
            return
        if tag in {"i", "em"}:
            self._append_text("*")
            return
        if tag == "u":
            self._append_text("_")
            return

        if tag in {"p", "div"}:
            self._ensure_blank_line()
            return

        if tag in {"ul", "ol"}:
            if self._list_depth:
                self._list_depth -= 1
            self._ensure_blank_line()
            return

        if tag == "li":
            self._ensure_newline()
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._ensure_blank_line()
            return

        if tag == "blockquote":
            if self._blockquote_depth:
                self._blockquote_depth -= 1
            self._ensure_blank_line()
            return

        if tag == "pre":
            if self._verbatim_depth:
                self._verbatim_depth -= 1
            self._ensure_blank_line()
            return

        if tag == "a" and self._anchor_stack:
            href, chunks = self._anchor_stack.pop()
            link_text = re.sub(r"\s+", " ", "".join(chunks)).strip()

            if not href:
                self._append_text(link_text)
                return

            if not link_text or link_text == href:
                self._append_text(href)
                return

            self._append_text(f"[{link_text}]({href})")

    @override
    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return

        if self._anchor_stack:
            _href, chunks = self._anchor_stack[-1]
            chunks.append(data)
            return

        self._append_text(data)


def _text_from_html(html_content: str) -> str:
    # Many templates end with "<p><em>The AlmaLinux Team</em></p>".
    # In plain text, render this as a conventional signature line.
    html_content = (html_content or "").replace(
        "<p><em>The AlmaLinux Team</em></p>",
        "<p>-- The AlmaLinux Team</p>",
    )
    parser = _TextFromHTMLParser()
    parser.feed(html_content)
    parser.close()
    return parser.text


def update_email_templates_and_remove_membership_request_approved(apps, schema_editor) -> None:
    EmailTemplate = apps.get_model("post_office", "EmailTemplate")

    templates: list[dict[str, str]] = [
        {
            "name": "election-voting-credential",
            "description": "Election voting credential email (and election announcement, basically)",
            "subject": "Your voting credential for {{ election_name }}",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>We are pleased to invite you to participate in the upcoming election: <strong>{{ election_name }}</strong>.</p>\n"
                "<p>{{ election_description }}</p>\n"
                "<p>Further information at: {{ election_url }}</p>\n\n"
                "<p>This election will be open from {{ election_start_datetime }} to {{ election_end_datetime }} (subject to meeting the minimum quota).</p>\n\n"
                "<hr>\n"
                "<h3>Your voting credential</h3>\n"
                "<p>Please keep this credential private. You will need it to access and submit your ballot.</p>\n"
                "<p><code>{{ credential_public_id }}</code></p>\n"
                "<p>Open the ballot using the link below. Your browser fills in the credential automatically; it is <strong>not</strong> sent to the server in the URL.</p>\n"
                "<p>  <a href=\"{{ vote_url_with_credential_fragment }}\">Open ballot</a></p>\n\n"
                "<hr>\n"
                "<h3>Important</h3>\n"
                "<ul>\n"
                "<li><strong>Do not share your credential.</strong></li>\n"
                "<li>If you submit multiple ballots, only your <strong>most recent submission</strong> before the election closes will be counted.</li>\n"
                "</ul>\n\n"
                "<p>If you have questions or encounter any issues, please contact <a href=\"mailto:elections@almalinux.org\">elections@almalinux.org</a>.</p>\n"
                "<p>Thank you for participating in the election!</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "election-vote-receipt",
            "description": "Election voting receipt",
            "subject": "Thank you for voting in {{ election_name }}",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Your vote for {{ election_name }} has been successfully recorded.</p>\n\n"
                "<hr>\n"
                "<h3>Your ballot receipt</h3>\n"
                "<p><strong>Ballot receipt code:</strong><br/><code>{{ ballot_hash }}</code></p>\n"
                "<p><strong>Submission nonce:</strong><br/><code>{{ nonce }}</code></p>\n"
                "<p>\nKeep both values private.</p>\n"
                "<ul>\n"
                "<li><strong>Receipt code:</strong> Allows you to verify that your ballot was received and counted.</li>\n"
                "<li><strong>Receipt code + nonce:</strong> Together allow you to verify the contents of your ballot.</li>\n"
                "</ul>\n"
                "<p>Do <strong>not</strong> share either value with anyone. Anyone with access to them may be able to verify or infer details about your vote.</p>\n"
                "<hr>\n"
                "<h3>Verify your ballot</h3>\n"
                "<p>You can verify that your ballot was recorded and included in the election ledger here:</p>\n"
                "<p>  <a href=\"{{ verify_url }}\">{{ verify_url }}</a></p>\n"
                "<p>This verification confirms that a ballot corresponding to your receipt exists in the system. It does <strong>not</strong> display your vote choices.</p>\n"
                "<hr>\n"
                "<h3>Ballot integrity ledger (advanced):</h3>\n"
                "<p>To make ballot storage tamper-evident, ballots are recorded in an append-only cryptographic ledger.</p>\n"
                "<ul>\n"
                "<li>Previous ledger hash: <code>{{ previous_chain_hash }}</code></li>\n"
                "<li>Current ledger hash:  <code>{{ chain_hash }}</code></li>\n"
                "</ul>\n"
                "<p>These values allow independent auditors to verify that ballots were not altered or removed after submission.</p>\n"
                "<hr>\n"
                "<h3>Important information</h3>\n"
                "<ul>\n"
                "<li>Only your <strong>most recent ballot</strong> submitted before the election closes will be counted.</li>\n"
                "<li>If you vote again, earlier ballots are automatically superseded.</li>\n"
                "<li>After the election is closed and tallied, <strong>all anonymized ballots and receipts will be published</strong>.</li>\n"
                "<li>You may then look for your receipt code in the published list to confirm that your ballot was included in the final count.</li>\n"
                "</ul>\n"
                "<h3>Privacy note</h3>\n"
                "<ul>\n"
                "<li>Your receipt does not display your vote choices.</li>\n"
                "<li>Ballots are published without voter identities.</li>\n"
                "<li>The system provides transparency and individual verification, but it does not prevent voters from voluntarily sharing their receipt.</li>\n"
                "</ul>\n"
                "<p>If you have questions or encounter any issues, please contact <a href=\"mailto:elections@almalinux.org\">elections@almalinux.org</a>.</p>\n"
                "<p>Thank you for participating in the election!</p>\n"
                "<p><em>The AlmaLinux Team</em></p>"
            ),
        },
        {
            "name": "membership-expiring-soon",
            "description": "Membership expiration warning",
            "subject": "Your membership expires in {{ days }} day{{ days|pluralize }}",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>This is a reminder that your <strong>{{ membership_type }}</strong> membership will expire in "
                "<strong>{{ days }} day{{ days|pluralize }}</strong>.</p>\n"
                "<p><strong>Expiration date:</strong> {{ expires_at }}</p>\n\n"
                "<hr>\n"
                "<h3>Renew your membership</h3>\n"
                "<p>To avoid any interruption to your membership benefits, please submit a renewal request:</p>\n"
                "<p>  <a href=\"{{ extend_url }}\">Renew membership</a></p>\n\n"
                "<p>If you have already renewed, you can safely ignore this email.</p>\n"
                "<p>Please feel free to contact <a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a> if you have any questions or concerns.</p>\n"
                "<p>Thank you for your continued support!</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "membership-expired",
            "description": "Membership expired notification",
            "subject": "Your membership has expired",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Your <strong>{{ membership_type }}</strong> membership has expired.</p>\n"
                "<p><strong>Expiration date:</strong> {{ expires_at }}</p>\n\n"
                "<hr>\n"
                "<h3>Renew your membership</h3>\n"
                "<p>You can restore your membership at any time by submitting a renewal request:</p>\n"
                "<p>  <a href=\"{{ extend_url }}\">Renew membership</a></p>\n\n"
                "<p>We appreciate your involvement and hope to welcome you back soon.</p>\n"
                "<p>Please feel free to contact <a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a> if you have any questions or concerns.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "membership-request-rejected",
            "description": "Membership request rejected",
            "subject": "Update on your membership application",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Thank you for applying for <strong>{{ membership_type }}</strong> membership with the AlmaLinux OS Foundation.</p>\n"
                "<p>After review, we are unable to approve your application at this time.</p>\n"
                "<p>{{ rejection_reason }}</p>\n"
                "<p>If your circumstances change, you are welcome to apply again in the future.</p>\n"
                "<p>Please contact <a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a> if you have any questions or would like clarification.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "membership-request-submitted",
            "description": "Membership request submitted",
            "subject": "Your membership application has been received",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Thank you for applying for <strong>{{ membership_type }}</strong> membership with the AlmaLinux OS Foundation.</p>\n"
                "<p>Your application has been received and will be reviewed by the membership committee.</p>\n"
                "<p>We will notify you by email once a decision has been made.</p>\n"
                "<p>If you have any questions in the meantime, please feel free to contact <a href=\"mailto:membership@almalinux.org\">membership@almalinux.org</a>.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "password-reset",
            "description": "Password reset email",
            "subject": "Password reset requested",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>We received a request to reset the password for your AlmaLinux account.</p>\n"
                "<hr>\n"
                "<h3>Reset your password</h3>\n"
                "<p>Use the link below to choose a new password:</p>\n"
                "<p>  <a href=\"{{ reset_url }}\">Reset password</a></p>\n"
                "<p>This link is valid for {{ ttl_minutes }} minutes (until {{ valid_until_utc }} UTC).</p>\n\n"
                "<p>If you did not request a password reset, you can safely ignore this email.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "password-reset-success",
            "description": "Password reset success email",
            "subject": "Your password has been reset",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Your AlmaLinux account password has been reset successfully.</p>\n"
                "<p>If you did not do this, <strong>please contact <a href=\"mailto:security@almalinux.org\">security@almalinux.org</a> immediately</strong>.</p>\n"
                "<p>  <a href=\"{{ login_url }}\">Log in</a></p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "registration-email-validation",
            "description": "Registration email validation",
            "subject": "Verify your email address to activate your account",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Welcome! Please verify your email address to activate your AlmaLinux account.</p>\n"
                "<hr>\n"
                "<h3>Verify your email address</h3>\n"
                "<p>  <a href=\"{{ activate_url }}\">Activate your account</a></p>\n"
                "<p>This link is valid for {{ ttl_minutes }} minutes (until {{ valid_until_utc }} UTC).</p>\n"
                "<p>If the link has expired, you can request a new verification email here:</p>\n"
                "<p>  <a href=\"{{ confirm_url }}\">Request a new link</a></p>\n"
                "<p>If you did not create this account, you can safely ignore this email.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
        {
            "name": "settings-email-validation",
            "description": "Email address validation for profile changes",
            "subject": "Verify your email address change",
            "html_content": (
                "<p>Hello {{ full_name }},</p>\n"
                "<p>Hello {{ full_name }},</p>\n"
                "<p>We received a request to add or change an email address for your AlmaLinux account "
                "<strong>{{ username }}</strong>.</p>\n"
                "<p>Please verify the email address <strong>{{ email_to_validate }}</strong> by using the link below. "
                "The change will not take effect until verification is complete.</p>\n"
                "<p>  <a href=\"{{ validate_url }}\">Verify this email address</a></p>\n"
                "<p>This link is valid for {{ ttl_minutes }} minutes (until {{ valid_until_utc }} UTC).</p>\n\n"
                "<p>If you did not request this change, you can safely ignore this email.</p>\n"
                "<p><em>The AlmaLinux Team</em></p>\n"
            ),
        },
    ]

    for spec in templates:
        html_content = spec["html_content"]
        EmailTemplate.objects.update_or_create(
            name=spec["name"],
            defaults={
                "description": spec["description"],
                "subject": spec["subject"],
                "html_content": html_content,
                "content": _text_from_html(html_content),
            },
        )

    EmailTemplate.objects.filter(name="membership-request-approved").delete()


def noop_reverse(apps, schema_editor) -> None:
    # Keep templates on rollback to avoid losing admin edits.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_organization_single_responsible"),
        ("post_office", "0013_email_recipient_delivery_status_alter_log_status"),
    ]

    operations = [
        migrations.RunPython(
            update_email_templates_and_remove_membership_request_approved,
            reverse_code=noop_reverse,
        ),
    ]
