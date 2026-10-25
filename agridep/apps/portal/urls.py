from django.urls import path
from .views import (
    home_view,
    about_view,
    value_chains_view,
    solutions_view,
    impact_view,
    contact_view,
    portal_login_view,
    cockpit_view,
    farms_geojson_view,
    resolve_duplicate_view,
    cockpit_upload_attendance_view,
    verify_certificate_view,
)

urlpatterns = [
    path('', home_view, name='home'),
    path('about/', about_view, name='about'),
    path('value-chains/', value_chains_view, name='value-chains'),
    path('solutions/', solutions_view, name='solutions'),
    path('impact/', impact_view, name='impact'),
    path('contact/', contact_view, name='contact'),
    path('login/', portal_login_view, name='portal-login'),
    
    # Milestone M2: DFAC Operational Cockpit & Map
    path('cockpit/', cockpit_view, name='cockpit'),
    path('cockpit/resolve-duplicate/<uuid:farmer_id>/', resolve_duplicate_view, name='cockpit-resolve-duplicate'),
    path('cockpit/upload-attendance/', cockpit_upload_attendance_view, name='cockpit-upload-attendance'),
    path('api/farms-geojson/', farms_geojson_view, name='farms-geojson'),
    
    # Milestone M2: Verifiable Credential Portal
    path('verify-certificate/', verify_certificate_view, name='verify-certificate'),
    path('verify-certificate/<str:code>/', verify_certificate_view, name='verify-certificate-detail'),
]
