from django.core.mail import send_mail
from django.test import TestCase
from django.test.utils import override_settings


@override_settings(
    EMAIL_BACKEND='post_office.EmailBackend',
    POST_OFFICE={
        'DEFAULT_PRIORITY': 'medium',
        'BACKENDS': {'default': 'django.core.mail.backends.locmem.EmailBackend'},
    },
)
class PostOfficeIntegrationTests(TestCase):
    def test_send_mail_creates_queued_email(self):
        from post_office.models import Email, STATUS

        send_mail('Subject', 'Body', 'from@example.com', ['to@example.com'])
        email = Email.objects.latest('id')

        self.assertEqual(email.subject, 'Subject')
        self.assertEqual(email.status, STATUS.queued)
