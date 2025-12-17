from django.urls import path

from . import views_selfservice as views

urlpatterns = [
    path('', views.profile, name='profile'),
    path('groups/', views.groups, name='groups'),

    path('settings/avatar/', views.avatar_manage, name='avatar-manage'),

    path('settings/profile/', views.settings_profile, name='settings-profile'),
    path('settings/emails/', views.settings_emails, name='settings-emails'),
    path('settings/keys/', views.settings_keys, name='settings-keys'),
    path('settings/otp/', views.settings_otp, name='settings-otp'),
    path('settings/password/', views.settings_password, name='settings-password'),
    path('settings/agreements/', views.settings_agreements, name='settings-agreements'),
]
