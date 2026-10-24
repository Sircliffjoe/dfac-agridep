from django.urls import path
from .views import KoboWebhookView, SyncPushView, SyncPullView

urlpatterns = [
    path('kobo/', KoboWebhookView.as_view(), name='kobo-webhook'),
    path('push/', SyncPushView.as_view(), name='sync-push'),
    path('pull/', SyncPullView.as_view(), name='sync-pull'),
]
