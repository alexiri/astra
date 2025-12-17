from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_ok(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/plain")
        self.assertEqual(response.content, b"ok")

    def test_healthz_does_not_depend_on_db(self):
        with patch("core.views_health.connection.cursor", side_effect=DatabaseError("boom")):
            response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_readyz_ok(self):
        response = self.client.get("/readyz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/plain")
        self.assertEqual(response.content, b"ok")

    def test_readyz_db_down_returns_503(self):
        with patch("core.views_health.connection.cursor", side_effect=DatabaseError("boom")):
            response = self.client.get("/readyz/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/plain")
