from django.urls import path

from . import views_registration

urlpatterns = [
    path("", views_registration.register, name="register"),
    path("confirm/", views_registration.confirm, name="register-confirm"),
    path("activate/", views_registration.activate, name="register-activate"),
]
