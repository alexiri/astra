import logging
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

logger = logging.getLogger(__name__)

try:

    from core.startup import ensure_membership_type_groups_exist

    ensure_membership_type_groups_exist()
except Exception:
	logger.exception("Startup membership group sync failed")
	raise
