from django.db import OperationalError, connection
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def health(request):
    """Report that the API is up and whether it can reach PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database = 'connected'
    except OperationalError:
        database = 'unavailable'
    return Response({'status': 'ok', 'database': database})
