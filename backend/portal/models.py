from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    display_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.display_name or self.username


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        UNPUBLISHED = 'unpublished', 'Unpublished'

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    content = models.TextField()  # sanitized HTML
    content_text = models.TextField(blank=True)  # plain text, used by search
    summary = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name='documents'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='documents')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='documents'
    )
    image = models.ImageField(upload_to='documents/', blank=True)
    image_alt = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    views_count = models.PositiveIntegerField(default=0)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)
    seo_keywords = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['published_at']),
        ]
        permissions = [
            ('publish_document', 'Can publish or unpublish documents'),
            ('edit_seo', 'Can edit SEO fields and alt text'),
        ]

    def __str__(self):
        return self.title


class Comment(models.Model):
    class Status(models.TextChoices):
        VISIBLE = 'visible', 'Visible'
        HIDDEN = 'hidden', 'Hidden'

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments'
    )
    body = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.VISIBLE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user} on {self.document}'


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes'
    )
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='likes'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'document'], name='unique_like'
            ),
        ]

    def __str__(self):
        return f'{self.user} likes {self.document}'


class UserTag(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_tags'
    )
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='user_tags'
    )
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='user_tags')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'document', 'tag'], name='unique_user_tag'
            ),
        ]

    def __str__(self):
        return f'{self.user} tagged {self.document} with {self.tag}'


class Report(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        RESOLVED = 'resolved', 'Resolved'

    comment = models.ForeignKey(
        Comment, on_delete=models.CASCADE, related_name='reports'
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports'
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_reports',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Report by {self.reporter} on comment {self.comment_id}'


class SearchClickLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='search_logs',
    )
    query_string = models.TextField()
    clicked_doc = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='search_clicks',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    query_id = models.UUIDField()
    position = models.PositiveIntegerField(null=True, blank=True)
    result_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['query_id']),
        ]
        permissions = [
            ('view_analytics', 'Can view the analytics dashboard'),
        ]

    def __str__(self):
        return f'{self.query_string} ({self.query_id})'


class SiteSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key
