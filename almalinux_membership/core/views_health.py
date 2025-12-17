from django.http import HttpResponse

from django.db import DatabaseError
from django.db import connection


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


def readyz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return HttpResponse("db unavailable", status=503, content_type="text/plain")

    return HttpResponse("ok", content_type="text/plain")
