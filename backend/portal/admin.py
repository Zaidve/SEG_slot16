from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Category, Comment, Document, Report, SiteSetting, Tag, User

# The only Document fields the Data & SEO role may change.
SEO_FIELDS = ('seo_title', 'seo_description', 'seo_keywords', 'image_alt')

# Adds the analytics link to the admin home page.
admin.site.index_template = 'portal/admin_index.html'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile', {'fields': ('display_name', 'avatar', 'bio')}),
    )
    # is_staff follows the user's roles, see signals.py.
    readonly_fields = ('is_staff',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'category', 'author', 'published_at', 'views_count')
    list_filter = ('status', 'category', 'tags', 'published_at')
    list_select_related = ('category', 'author')
    search_fields = ('title', 'summary', 'content_text')
    filter_horizontal = ('tags',)
    actions = ('publish', 'unpublish')
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'summary', 'content', 'content_text')}),
        ('Classification', {'fields': ('category', 'tags', 'author')}),
        ('Image', {'fields': ('image', 'image_alt')}),
        ('Publishing', {
            'fields': ('status', 'published_at', 'views_count', 'created_at', 'updated_at'),
        }),
        ('SEO', {'fields': ('seo_title', 'seo_description', 'seo_keywords')}),
    )
    readonly_fields = ('content_text', 'published_at', 'views_count', 'created_at', 'updated_at')

    def has_change_permission(self, request, obj=None):
        # Data & SEO has no change_document, but may open the form to edit SEO.
        return (
            super().has_change_permission(request, obj)
            or request.user.has_perm('portal.edit_seo')
        )

    def has_publish_permission(self, request):
        return request.user.has_perm('portal.publish_document')

    def get_readonly_fields(self, request, obj=None):
        user = request.user
        if not user.has_perm('portal.change_document'):
            return [f for f in flatten_fieldsets(self.fieldsets) if f not in SEO_FIELDS]
        readonly = list(self.readonly_fields)
        if not user.has_perm('portal.publish_document'):
            readonly.append('status')
        if not user.has_perm('portal.change_user'):
            readonly.append('author')
        return readonly

    def get_prepopulated_fields(self, request, obj=None):
        # The admin crashes if a read-only field is prepopulated.
        if request.user.has_perm('portal.change_document'):
            return {'slug': ('title',)}
        return {}

    def get_changeform_initial_data(self, request):
        return {**super().get_changeform_initial_data(request), 'author': request.user.pk}

    def save_model(self, request, obj, form, change):
        if not change and not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    def set_status(self, request, queryset, status, label):
        # Save one at a time so Document.save() runs and the change is logged.
        for document in queryset:
            document.status = status
            document.save()
            self.log_change(request, document, label)
        self.message_user(request, f'{label}: {len(queryset)} document(s).')

    @admin.action(description='Publish selected documents', permissions=['publish'])
    def publish(self, request, queryset):
        self.set_status(request, queryset, Document.Status.PUBLISHED, 'Published')

    @admin.action(description='Unpublish selected documents', permissions=['publish'])
    def unpublish(self, request, queryset):
        self.set_status(request, queryset, Document.Status.UNPUBLISHED, 'Unpublished')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('body', 'user', 'document', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    list_select_related = ('user', 'document')
    search_fields = ('body', 'user__username')
    actions = ('hide',)
    # Moderators can hide a comment but not rewrite what someone said.
    readonly_fields = ('document', 'user', 'body', 'created_at')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Hide selected comments', permissions=['change'])
    def hide(self, request, queryset):
        for comment in queryset:
            comment.status = Comment.Status.HIDDEN
            comment.save()
            self.log_change(request, comment, 'Hidden')
        self.message_user(request, f'Hidden: {len(queryset)} comment(s).')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('comment_body', 'reason', 'reporter', 'status', 'resolved_by', 'created_at')
    list_filter = ('status', 'created_at')
    list_select_related = ('comment', 'reporter', 'resolved_by')
    search_fields = ('reason', 'comment__body')
    actions = ('resolve',)
    # Resolve through the action, so resolved_by is always recorded.
    readonly_fields = (
        'comment', 'comment_body', 'reporter', 'reason', 'status', 'resolved_by', 'created_at',
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description='Comment')
    def comment_body(self, report):
        return report.comment.body

    @admin.action(description='Resolve selected reports', permissions=['change'])
    def resolve(self, request, queryset):
        # Skip resolved reports so the first resolver stays on record.
        reports = queryset.filter(status=Report.Status.OPEN)
        for report in reports:
            report.status = Report.Status.RESOLVED
            report.resolved_by = request.user
            report.save()
            self.log_change(request, report, 'Resolved')
        self.message_user(request, 'Selected open reports were resolved.')


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key',)


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    """System logs: read-only, and only Super Admin has view_logentry."""

    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message')
    list_filter = ('action_flag', 'action_time', 'content_type')
    search_fields = ('object_repr', 'change_message', 'user__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
