from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Category, Comment, Document, Report, Tag, User


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'display_name')
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, attrs):
        user = User(username=attrs['username'], email=attrs.get('email', ''))
        try:
            validate_password(attrs['password'], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'password': error.messages})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(self.context['request'], **attrs)
        if user is None:
            raise serializers.ValidationError('Wrong username or password.')
        attrs['user'] = user
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'display_name', 'avatar', 'bio')
        read_only_fields = ('id', 'username', 'email')


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'slug')


class DocumentListSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    tags = TagSerializer(many=True)
    author = serializers.StringRelatedField()

    class Meta:
        model = Document
        fields = (
            'id', 'title', 'slug', 'summary', 'image', 'image_alt', 'category',
            'tags', 'author', 'published_at', 'views_count',
        )


class DocumentDetailSerializer(DocumentListSerializer):
    like_count = serializers.IntegerField(source='likes.count')
    liked = serializers.SerializerMethodField()
    user_tags = serializers.SerializerMethodField()

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + (
            'content', 'updated_at', 'seo_title', 'seo_description', 'seo_keywords',
            'like_count', 'liked', 'user_tags',
        )

    def get_liked(self, document):
        user = self.context['request'].user
        return user.is_authenticated and document.likes.filter(user=user).exists()

    def get_user_tags(self, document):
        tags = Tag.objects.filter(user_tags__document=document).distinct()
        return TagSerializer(tags, many=True).data


class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    body = serializers.CharField(max_length=2000)

    class Meta:
        model = Comment
        fields = ('id', 'user', 'body', 'created_at')


class UserTagSerializer(serializers.Serializer):
    # Readers choose an existing tag. Creating tags is a Content Manager job.
    tag = serializers.SlugRelatedField(slug_field='slug', queryset=Tag.objects.all())


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ('id', 'reason', 'status', 'created_at')
        read_only_fields = ('id', 'status', 'created_at')


class SearchClickSerializer(serializers.Serializer):
    query_id = serializers.UUIDField()
    document = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.filter(status=Document.Status.PUBLISHED)
    )
    position = serializers.IntegerField(min_value=1)
