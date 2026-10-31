import uuid

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.db import Error, connection
from django.db.models import F
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Category,
    Comment,
    Document,
    Like,
    Report,
    SearchClickLog,
    Tag,
    UserTag,
)
from .search import search_documents
from .serializers import (
    CategorySerializer,
    CommentSerializer,
    DocumentDetailSerializer,
    DocumentListSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ReportSerializer,
    SearchClickSerializer,
    TagSerializer,
    UserTagSerializer,
)


class CsrfSessionAuthentication(SessionAuthentication):
    """Check CSRF for guests too. DRF normally checks logged-in users only."""

    def authenticate(self, request):
        self.enforce_csrf(request)
        return super().authenticate(request)


def published_documents():
    return Document.objects.filter(status=Document.Status.PUBLISHED)


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


@api_view(['GET'])
def csrf(request):
    get_token(request)  # makes Django send the csrftoken cookie
    return Response({'detail': 'CSRF cookie set.'})


@api_view(['POST'])
@authentication_classes([CsrfSessionAuthentication])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    auth_login(request, user)
    data = ProfileSerializer(user, context={'request': request}).data
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([CsrfSessionAuthentication])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data['user']
    auth_login(request, user)
    return Response(ProfileSerializer(user, context={'request': request}).data)


@api_view(['POST'])
@authentication_classes([CsrfSessionAuthentication])
@permission_classes([AllowAny])
def logout(request):
    auth_logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user


class DocumentListView(generics.ListAPIView):
    serializer_class = DocumentListSerializer
    queryset = (
        published_documents()
        .select_related('category', 'author')
        .prefetch_related('tags')
        .order_by('-published_at', '-id')  # id keeps pages stable on equal dates
    )


@api_view(['GET'])
def document_detail(request, slug):
    document = get_object_or_404(published_documents(), slug=slug)
    # F() lets the database add 1, so two readers at once both count.
    Document.objects.filter(pk=document.pk).update(views_count=F('views_count') + 1)
    document.refresh_from_db(fields=['views_count'])
    serializer = DocumentDetailSerializer(document, context={'request': request})
    return Response(serializer.data)


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    pagination_class = None


class TagListView(generics.ListAPIView):
    serializer_class = TagSerializer
    queryset = Tag.objects.all()
    pagination_class = None


class CommentListView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer

    def get_document(self):
        return get_object_or_404(published_documents(), pk=self.kwargs['pk'])

    def get_queryset(self):
        comments = self.get_document().comments
        return comments.filter(status=Comment.Status.VISIBLE).select_related('user')

    def perform_create(self, serializer):
        serializer.save(document=self.get_document(), user=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_like(request, pk):
    document = get_object_or_404(published_documents(), pk=pk)
    like, created = Like.objects.get_or_create(user=request.user, document=document)
    if not created:
        like.delete()
    return Response({'liked': created, 'like_count': document.likes.count()})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_user_tag(request, pk):
    document = get_object_or_404(published_documents(), pk=pk)
    serializer = UserTagSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    tag = serializer.validated_data['tag']
    _, created = UserTag.objects.get_or_create(
        user=request.user, document=document, tag=tag
    )
    return Response(
        TagSerializer(tag).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_comment(request, pk):
    comment = get_object_or_404(
        Comment,
        pk=pk,
        status=Comment.Status.VISIBLE,
        document__status=Document.Status.PUBLISHED,
    )
    already_reported = Report.objects.filter(
        comment=comment, reporter=request.user, status=Report.Status.OPEN
    ).exists()
    if already_reported:
        return Response(
            {'detail': 'You have already reported this comment.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = ReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(comment=comment, reporter=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


def text_param(request, name):
    # PostgreSQL rejects NUL characters, so a crafted URL could cause a 500.
    return request.query_params.get(name, '').replace('\x00', '').strip()


def date_param(request, name):
    value = text_param(request, name)
    if not value:
        return None
    try:
        date = parse_date(value)
    except ValueError:  # the right shape but not a real date, like 2026-02-31
        date = None
    if date is None:
        raise ValidationError({name: 'Enter a date as YYYY-MM-DD.'})
    return date


def existing_query_id(request, query):
    """Return the query_id sent by a later page of this search, if it is real."""
    try:
        query_id = uuid.UUID(text_param(request, 'query_id'))
    except ValueError:
        return None
    rows = SearchClickLog.objects.filter(query_id=query_id, query_string=query)
    return query_id if rows.exists() else None


@api_view(['GET'])
def search(request):
    query = text_param(request, 'q')
    filters = {
        'category': text_param(request, 'category'),
        'tag': text_param(request, 'tag'),
        'from': date_param(request, 'from'),
        'to': date_param(request, 'to'),
    }
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(search_documents(query, filters), request)

    # Moving to another page is the same search, so it does not log a new row.
    query_id = existing_query_id(request, query)
    if query_id is None:
        query_id = uuid.uuid4()
        SearchClickLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            query_string=query,
            query_id=query_id,
            result_count=paginator.page.paginator.count,
        )

    serializer = DocumentListSerializer(page, many=True, context={'request': request})
    response = paginator.get_paginated_response(serializer.data)
    response.data['query_id'] = query_id
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def search_click(request):
    serializer = SearchClickSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    click = serializer.validated_data
    # Copy the query from the search row instead of trusting the client.
    search_row = get_object_or_404(
        SearchClickLog, query_id=click['query_id'], position__isnull=True
    )
    if click['position'] > search_row.result_count:
        raise ValidationError({'position': 'This search has fewer results.'})
    SearchClickLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        query_string=search_row.query_string,
        clicked_doc=click['document'],
        query_id=search_row.query_id,
        position=click['position'],
        result_count=search_row.result_count,
    )
    return Response(status=status.HTTP_201_CREATED)
