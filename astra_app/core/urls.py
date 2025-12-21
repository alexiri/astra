from django.urls import path

from core import views_groups, views_settings, views_settings_otp, views_users

urlpatterns = [
    path("", views_users.home, name="home"),
    path("users/", views_users.users, name="users"),
    path("user/<str:username>/", views_users.user_profile, name="user-profile"),
    path("groups/", views_groups.groups, name="groups"),

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
]
