from django.test import SimpleTestCase
from django.urls import reverse


class DjangoSesUrlsTests(SimpleTestCase):
    def test_event_webhook_url_is_wired(self):
        # Name used by django-ses upstream docs/tests.
        self.assertEqual(reverse('event_webhook'), '/ses/event-webhook/')

    def test_stats_dashboard_url_is_wired(self):
        # Provided by django_ses.urls include.
        self.assertEqual(reverse('django_ses_stats'), '/admin/django-ses/')
