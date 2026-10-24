from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse, HttpResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

def home_view(request):
    """Developer and operator landing page with direct links."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DFAC AgriDEP Platform</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f0fdf4; color: #1e293b; margin: 0; padding: 40px 20px; }
        .card { max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1); border: 1px solid #bbf7d0; }
        h1 { color: #007a33; margin-top: 0; }
        .tagline { color: #047857; font-weight: 500; font-size: 1.1em; margin-bottom: 24px; }
        .badge { display: inline-block; background: #dcfce7; color: #15803d; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; font-weight: 600; margin-right: 8px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 24px; }
        .btn { display: block; text-align: center; background: #007a33; color: white; text-decoration: none; padding: 12px 18px; border-radius: 8px; font-weight: 600; transition: background 0.2s; }
        .btn:hover { background: #005a26; }
        .btn-secondary { background: #f1f5f9; color: #0f172a; border: 1px solid #cbd5e1; }
        .btn-secondary:hover { background: #e2e8f0; }
        .info { margin-top: 28px; background: #f8fafc; border-left: 4px solid #007a33; padding: 16px; border-radius: 4px; font-size: 0.95em; }
        code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="card">
        <div>
            <span class="badge">Milestones M0 & M1 Ready</span>
            <span class="badge">Python 3.14.4</span>
            <span class="badge">Django 6.1.2</span>
            <span class="badge">Dokku VPS Ready</span>
        </div>
        <h1>Doctor Fish Agricultural Consult (DFAC)</h1>
        <div class="tagline">AgriDEP: Agricultural Data Ecosystem Platform</div>
        <p>Connecting Farmers, Data, Finance, and Markets across rural Niger Delta (Delta, Bayelsa, and Rivers states).</p>

        <div class="grid">
            <a href="/api/v1/schema/swagger-ui/" class="btn">🚀 Interactive Swagger UI</a>
            <a href="/admin/" class="btn">🛡️ Django Admin Cockpit</a>
            <a href="/api/v1/schema/redoc/" class="btn btn-secondary">📖 ReDoc API Guide</a>
            <a href="/api/v1/health/" class="btn btn-secondary">💚 System Healthcheck</a>
        </div>

        <div class="info">
            <strong>Default Demo Credentials:</strong>
            <ul>
                <li><strong>DFAC Admin:</strong> <code>admin</code> / <code>admin12345</code></li>
                <li><strong>Field Officer:</strong> <code>officer_delta</code> / <code>password123</code></li>
                <li><strong>Commercial Buyer:</strong> <code>buyer_aggregator</code> / <code>password123</code></li>
            </ul>
            <strong>Quick Endpoints:</strong>
            <ul>
                <li>Farmer Registry: <a href="/api/v1/registry/farmers/"><code>/api/v1/registry/farmers/</code></a></li>
                <li>Production Cycles: <a href="/api/v1/production/cycles/"><code>/api/v1/production/cycles/</code></a></li>
                <li>KoboToolbox Webhook: <code>/api/v1/sync/kobo/</code></li>
                <li>Flutter Drift Delta Sync: <code>/api/v1/sync/pull/</code></li>
            </ul>
        </div>
    </div>
</body>
</html>"""
    return HttpResponse(html)

def health_check(request):
    """Zero-downtime Dokku healthcheck endpoint."""
    return JsonResponse({"status": "ok", "service": "DFAC AgriDEP API"})

urlpatterns = [
    path('', home_view, name='home'),
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
