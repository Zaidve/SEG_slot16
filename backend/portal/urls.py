from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health),
    path('auth/csrf', views.csrf),
    path('auth/register', views.register),
    path('auth/login', views.login),
    path('auth/logout', views.logout),
    path('profile', views.ProfileView.as_view()),
    path('documents', views.DocumentListView.as_view()),
    path('documents/<int:pk>/comments', views.CommentListView.as_view()),
    path('documents/<int:pk>/like', views.toggle_like),
    path('documents/<int:pk>/tags', views.add_user_tag),
    path('documents/<slug:slug>', views.document_detail),
    path('categories', views.CategoryListView.as_view()),
    path('tags', views.TagListView.as_view()),
    path('comments/<int:pk>/report', views.report_comment),
]
