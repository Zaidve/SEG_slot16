from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.db import Error, connection
from django.db.models import F
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Category, Comment, Document, Like, Report, Tag, UserTag
from .serializers import (
    CategorySerializer,
    CommentSerializer,
    DocumentDetailSerializer,
    DocumentListSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ReportSerializer,
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
