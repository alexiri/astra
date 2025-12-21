from django.urls import path

from . import views_selfservice as views

urlpatterns = [
    path('', views.home, name='home'),
    path('users/', views.users, name='users'),
    path('user/<str:username>/', views.user_profile, name='user-profile'),
    path('groups/', views.groups, name='groups'),

    path('settings/avatar/', views.avatar_manage, name='avatar-manage'),

    path('settings/profile/', views.settings_profile, name='settings-profile'),
    path('settings/emails/', views.settings_emails, name='settings-emails'),
    path('settings/emails/validate/', views.settings_email_validate, name='settings-email-validate'),
    path('settings/keys/', views.settings_keys, name='settings-keys'),
    path('settings/otp/', views.settings_otp, name='settings-otp'),
    path('settings/otp/enable/', views.otp_enable, name='otp-enable'),
    path('settings/otp/disable/', views.otp_disable, name='otp-disable'),
    path('settings/otp/delete/', views.otp_delete, name='otp-delete'),
    path('settings/otp/rename/', views.otp_rename, name='otp-rename'),
    path('settings/password/', views.settings_password, name='settings-password'),
    path('settings/agreements/', views.settings_agreements, name='settings-agreements'),
]
