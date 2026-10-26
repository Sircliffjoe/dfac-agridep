from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Customize Admin Site Branding
admin.site.site_header = "DFAC AgriDEP Operations Console"
admin.site.site_title = "DFAC AgriDEP"
admin.site.index_title = "Agricultural Data Ecosystem Platform"

def health_check(request):
    """Zero-downtime Dokku healthcheck endpoint."""
    return JsonResponse({"status": "ok", "service": "DFAC AgriDEP API"})

urlpatterns = [
    # Public & Stakeholder Portal Pages
    path('', include('agridep.apps.portal.urls')),
    
    # Operations Administration
    path('admin/', admin.site.urls),
    
    # Internal Healthcheck
    path('api/v1/health/', health_check, name='health-check'),
    
    # OpenAPI Schema & Docs
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # REST API endpoints
    path('api/v1/auth/', include('agridep.apps.accounts.urls')),
    path('api/v1/registry/', include('agridep.apps.registry.urls')),
    path('api/v1/production/', include('agridep.apps.production.urls')),
    path('api/v1/training/', include('agridep.apps.training.urls')),
    path('api/v1/finance/', include('agridep.apps.finance.urls')),
    path('api/v1/market/', include('agridep.apps.market.urls')),
    path('api/v1/fieldops/', include('agridep.apps.fieldops.api.urls')),
    path('api/v1/alerts/', include('agridep.apps.alerts.api.urls')),
    path('api/v1/inputs/', include('agridep.apps.inputs.api.urls')),
    path('api/v1/reporting/', include('agridep.apps.reporting.api.urls')),
    path('api/v1/sync/', include('agridep.apps.sync.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

