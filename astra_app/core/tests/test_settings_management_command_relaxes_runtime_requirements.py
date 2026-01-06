import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class TestSettingsManagementCommandRelaxesRuntimeRequirements(unittest.TestCase):
    @staticmethod
    def _django_project_dir() -> Path:
        # Works in both layouts:
        # - image: /app/astra_app/astra_app/core/tests/... -> project dir is /app/astra_app/astra_app
        # - bind mount: /app/astra_app/core/tests/... -> project dir is /app/astra_app
        return Path(__file__).resolve().parents[2]

    def test_migrate_does_not_require_runtime_secrets(self) -> None:
        project_dir = self._django_project_dir()
        env = {
            "DEBUG": "0",
            "DATABASE_HOST": "db.example.internal",
            "DATABASE_PORT": "5432",
            "DATABASE_NAME": "astra",
            "DATABASE_USER": "astra",
            "DATABASE_PASSWORD": "supersecret",
        }

        code = textwrap.dedent(
            f"""
            import sys

            sys.path.insert(0, {str(project_dir)!r})

            # Simulate `python manage.py migrate`.
            sys.argv = ["manage.py", "migrate", "--noinput"]
            import config.settings  # noqa: F401
            print("ok")
            """
        ).strip()

        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"settings import failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        # settings.py may emit debug output; assert the final line is the sentinel.
        self.assertEqual(result.stdout.strip().splitlines()[-1], "ok")

    def test_web_runtime_still_requires_secret_key(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "DEBUG": "0",
                "ALLOWED_HOSTS": "example.com",
                "FREEIPA_SERVICE_PASSWORD": "password",
                "AWS_STORAGE_BUCKET_NAME": "astra-media",
                "AWS_S3_DOMAIN": "http://localhost:9000",
                "DATABASE_HOST": "db.example.internal",
                "DATABASE_PORT": "5432",
                "DATABASE_NAME": "astra",
                "DATABASE_USER": "astra",
                "DATABASE_PASSWORD": "supersecret",
            }
        )
        env.pop("DATABASE_URL", None)
        env.pop("SECRET_KEY", None)

        code = textwrap.dedent(
            """
            import os
            import sys

            sys.path.insert(0, os.path.join(os.getcwd(), "astra_app"))

            # Simulate a non-management runtime argv (e.g. gunicorn).
            sys.argv = ["gunicorn", "config.wsgi:application"]

            import config.settings  # noqa: F401

            print("unexpected")
            """
        ).strip()

        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be set in production", result.stderr)
