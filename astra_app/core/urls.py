from django.urls import path

from core import (
    views_groups,
    views_membership,
    views_organizations,
    views_search,
    views_settings,
    views_settings_otp,
    views_users,
)

urlpatterns = [
    path("", views_users.home, name="home"),
    path("users/", views_users.users, name="users"),
    path("user/<str:username>/", views_users.user_profile, name="user-profile"),
    path("groups/", views_groups.groups, name="groups"),
    path("group/<str:name>/", views_groups.group_detail, name="group-detail"),

    path("organizations/", views_organizations.organizations, name="organizations"),
    path("organization/<str:code>/", views_organizations.organization_detail, name="organization-detail"),
    path("organization/<str:code>/edit/", views_organizations.organization_edit, name="organization-edit"),

    path("search/", views_search.global_search, name="global-search"),

    path("membership/request/", views_membership.membership_request, name="membership-request"),
    path("membership/requests/", views_membership.membership_requests, name="membership-requests"),
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
