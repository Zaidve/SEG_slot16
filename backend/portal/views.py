from django.db import Error, connection
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def health(request):
    """Report that the API is up and whether it can reach PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Error:
        return Response(
            {'status': 'error', 'database': 'unavailable'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({'status': 'ok', 'database': 'connected'})
