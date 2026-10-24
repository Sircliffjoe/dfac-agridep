from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

def health_check(request):
    """Zero-downtime Dokku healthcheck endpoint."""
    return JsonResponse({"status": "ok", "service": "DFAC AgriDEP API"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check, name='health-check'),
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API endpoints
    path('api/v1/auth/', include('agridep.apps.accounts.urls')),
    path('api/v1/registry/', include('agridep.apps.registry.urls')),
    path('api/v1/production/', include('agridep.apps.production.urls')),
    path('api/v1/sync/', include('agridep.apps.sync.urls')),
]
