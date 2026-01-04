from django.urls import path

from core import (
    views_elections,
    views_groups,
    views_mailmerge,
    views_membership,
    views_organizations,
    views_search,
    views_settings,
    views_settings_otp,
    views_templated_email,
    views_users,
)

urlpatterns = [
    path("", views_users.home, name="home"),
    path("users/", views_users.users, name="users"),
    path("user/<str:username>/", views_users.user_profile, name="user-profile"),
    path("groups/", views_groups.groups, name="groups"),
    path("groups/search/", views_groups.group_search, name="group-search"),
    path("group/<str:name>/", views_groups.group_detail, name="group-detail"),

    path("organizations/", views_organizations.organizations, name="organizations"),
    path("organizations/create/", views_organizations.organization_create, name="organization-create"),
    path(
        "organizations/representatives/search/",
        views_organizations.organization_representatives_search,
        name="organization-representatives-search",
    ),
    path("organization/<int:organization_id>/", views_organizations.organization_detail, name="organization-detail"),
    path(
        "organization/<int:organization_id>/sponsorship/extend/",
        views_organizations.organization_sponsorship_extend,
        name="organization-sponsorship-extend",
    ),
    path(
        "organization/<int:organization_id>/sponsorship/<str:membership_type_code>/expiry/",
        views_membership.organization_sponsorship_set_expiry,
        name="organization-sponsorship-set-expiry",
    ),
    path(
        "organization/<int:organization_id>/sponsorship/<str:membership_type_code>/terminate/",
        views_membership.organization_sponsorship_terminate,
        name="organization-sponsorship-terminate",
    ),
    path("organization/<int:organization_id>/edit/", views_organizations.organization_edit, name="organization-edit"),
    path(
        "organization/<int:organization_id>/committee-notes/",
        views_organizations.organization_committee_notes_update,
        name="organization-committee-notes-update",
    ),

    path("search/", views_search.global_search, name="global-search"),

    path("elections/", views_elections.elections_list, name="elections"),
    path("elections/ballot/verify/", views_elections.ballot_verify, name="ballot-verify"),
    path("elections/<int:election_id>/edit/", views_elections.election_edit, name="election-edit"),
    path(
        "elections/<int:election_id>/eligible-users/search/",
        views_elections.election_eligible_users_search,
        name="election-eligible-users-search",
    ),
    path(
        "elections/<int:election_id>/nomination-users/search/",
        views_elections.election_nomination_users_search,
        name="election-nomination-users-search",
    ),
    path(
        "elections/<int:election_id>/email/render-preview/",
        views_elections.election_email_render_preview,
        name="election-email-render-preview",
    ),
    path("elections/<int:election_id>/", views_elections.election_detail, name="election-detail"),
    path("elections/<int:election_id>/vote/", views_elections.election_vote, name="election-vote"),

    path(
        "elections/<int:election_id>/resend-credentials/",
        views_elections.election_resend_credentials,
        name="election-resend-credentials",
    ),

    path("elections/<int:election_id>/extend-end/", views_elections.election_extend_end, name="election-extend-end"),

    path(
        "elections/<int:election_id>/conclude/",
        views_elections.election_conclude,
        name="election-conclude",
    ),

    path(
        "elections/<int:election_id>/public/ballots.json",
        views_elections.election_public_ballots,
        name="election-public-ballots",
    ),
    path(
        "elections/<int:election_id>/public/audit.json",
        views_elections.election_public_audit,
        name="election-public-audit",
    ),
    path(
        "elections/<int:election_id>/audit/",
        views_elections.election_audit_log,
        name="election-audit-log",
    ),
    path(
        "elections/<int:election_id>/vote/submit.json",
        views_elections.election_vote_submit,
        name="election-vote-submit",
    ),

    path("email-tools/mail-merge/", views_mailmerge.mail_merge, name="mail-merge"),
    path(
        "email-tools/mail-merge/render-preview/",
        views_mailmerge.mail_merge_render_preview,
        name="mail-merge-render-preview",
    ),

    path(
        "email-tools/templates/<int:template_id>/json/",
        views_templated_email.email_template_json,
        name="email-template-json",
    ),
    path(
        "email-tools/templates/render-preview/",
        views_templated_email.email_template_render_preview,
        name="email-template-render-preview",
    ),
    path(
        "email-tools/templates/save/",
        views_templated_email.email_template_save,
        name="email-template-save",
    ),
    path(
        "email-tools/templates/save-as/",
        views_templated_email.email_template_save_as,
        name="email-template-save-as",
    ),

    path(
        "email-tools/templates/",
        views_templated_email.email_templates,
        name="email-templates",
    ),
    path(
        "email-tools/templates/new/",
        views_templated_email.email_template_create,
        name="email-template-create",
    ),
    path(
        "email-tools/templates/<int:template_id>/",
        views_templated_email.email_template_edit,
        name="email-template-edit",
    ),
    path(
        "email-tools/templates/<int:template_id>/delete/",
        views_templated_email.email_template_delete,
        name="email-template-delete",
    ),

    path("membership/request/", views_membership.membership_request, name="membership-request"),
    path("membership/requests/", views_membership.membership_requests, name="membership-requests"),
    path(
        "membership/requests/<int:pk>/",
        views_membership.membership_request_detail,
        name="membership-request-detail",
    ),
    path(
        "membership/requests/bulk/",
        views_membership.membership_requests_bulk,
        name="membership-requests-bulk",
    ),
    path(
        "membership/requests/<int:pk>/approve/",
        views_membership.membership_request_approve,
        name="membership-request-approve",
    ),
    path(
        "membership/requests/<int:pk>/reject/",
        views_membership.membership_request_reject,
        name="membership-request-reject",
    ),
    path(
        "membership/requests/<int:pk>/ignore/",
        views_membership.membership_request_ignore,
        name="membership-request-ignore",
    ),

    path("membership/log/", views_membership.membership_audit_log, name="membership-audit-log"),
    path(
        "membership/log/org/<int:organization_id>/",
        views_membership.membership_audit_log_organization,
        name="membership-audit-log-organization",
    ),
    path(
        "membership/log/<str:username>/",
        views_membership.membership_audit_log_user,
        name="membership-audit-log-user",
    ),

    path(
        "membership/manage/<str:username>/<str:membership_type_code>/expiry/",
        views_membership.membership_set_expiry,
        name="membership-set-expiry",
    ),
    path(
        "membership/manage/<str:username>/<str:membership_type_code>/terminate/",
        views_membership.membership_terminate,
        name="membership-terminate",
    ),

    path(
        "membership/manage/<str:username>/status-note/",
        views_membership.membership_status_note_update,
        name="membership-status-note-update",
    ),

    path("settings/avatar/", views_settings.avatar_manage, name="avatar-manage"),

    path("settings/profile/", views_settings.settings_profile, name="settings-profile"),
    path("settings/emails/", views_settings.settings_emails, name="settings-emails"),
    path("settings/emails/validate/", views_settings.settings_email_validate, name="settings-email-validate"),
    path("settings/keys/", views_settings.settings_keys, name="settings-keys"),
    path("settings/otp/", views_settings_otp.settings_otp, name="settings-otp"),
    path("settings/otp/enable/", views_settings_otp.otp_enable, name="otp-enable"),
    path("settings/otp/disable/", views_settings_otp.otp_disable, name="otp-disable"),
    path("settings/otp/delete/", views_settings_otp.otp_delete, name="otp-delete"),
    path("settings/otp/rename/", views_settings_otp.otp_rename, name="otp-rename"),
    path("settings/password/", views_settings.settings_password, name="settings-password"),
    path("settings/agreements/", views_settings.settings_agreements, name="settings-agreements"),
    path(
        "settings/agreements/<str:cn>/",
        views_settings.settings_agreement_detail,
        name="settings-agreement-detail",
    ),
]
