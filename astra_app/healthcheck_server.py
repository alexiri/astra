#!/usr/bin/env python3
"""
Standalone health check server on port 9000.
Runs alongside Django to serve internal health checks without ALLOWED_HOSTS validation.
"""
import http.server
import json
import logging
import os
import socketserver
import sys
import traceback
from pathlib import Path

# Add parent directory to path for Django imports
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connection

logger = logging.getLogger('healthcheck_server')


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/healthz/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        elif self.path in ("/readyz", "/readyz/"):
            try:
                connection.ensure_connection()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ready", "database": "ok"}).encode())
            except Exception as e:
                logger.error(
                    "Health check readyz failed: %s",
                    str(e),
                    exc_info=True,
                    extra={"path": self.path}
                )
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "not ready", "error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress successful health check access logs (200 OK)
        # but allow other status codes through for debugging
        # if "200" not in str(args):
        #     logger.info(format % args)
        logger.info(format % args)


if __name__ == "__main__":
    PORT = 9000
    
    # Configure logging to use Django's logging setup
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s healthcheck_server: %(message)s',
        stream=sys.stdout
    )
    
    logger.info("Health check server starting on port %d", PORT)
    
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        logger.info("Health check server running on port %d", PORT)
        httpd.serve_forever()
