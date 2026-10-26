from django.urls import path
from .views import KoboWebhookView, SyncPushView, SyncPullView, MediaUploadView

urlpatterns = [
    path('kobo/', KoboWebhookView.as_view(), name='kobo-webhook'),
    path('push/', SyncPushView.as_view(), name='sync-push'),
    path('pull/', SyncPullView.as_view(), name='sync-pull'),
    path('media/upload/', MediaUploadView.as_view(), name='sync-media-upload'),
]
