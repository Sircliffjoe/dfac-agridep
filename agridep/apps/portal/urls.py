from django.urls import path
from .views import (
    home_view,
    about_view,
    value_chains_view,
    solutions_view,
    impact_view,
    contact_view,
    portal_login_view,
    portal_logout_view,
    portal_dashboard_view,
    trainer_portal_view,
    trainer_schedule_session_portal,
    trainer_issue_certificate_portal,
    farmer_portal_view,
    user_profile_view,
    admin_console_view,
    admin_toggle_user_status_view,
    admin_change_user_role_view,
    admin_create_user_view,
    admin_verify_farmer_view,
    cockpit_view,
    farms_geojson_view,
    resolve_duplicate_view,
    cockpit_upload_attendance_view,
    verify_certificate_view,
    lender_portal_view,
    buyer_portal_view,
    confirm_produce_match_portal,
    trigger_auto_match_portal,
    field_officer_portal_view,
    fieldops_log_visit_portal,
    fieldops_report_incident_portal,
    fieldops_auto_dispatch_portal,
    ussd_simulator_view,
    donor_reporting_portal_view,
    inputs_portal_view,
    confirm_input_delivery_portal,
    download_apk_view,
)

urlpatterns = [
    path('', home_view, name='home'),
    path('about/', about_view, name='about'),
    path('value-chains/', value_chains_view, name='value-chains'),
    path('solutions/', solutions_view, name='solutions'),
    path('impact/', impact_view, name='impact'),
    path('contact/', contact_view, name='contact'),
    path('login/', portal_login_view, name='portal-login'),
    path('logout/', portal_logout_view, name='portal-logout'),
    path('portal/dashboard/', portal_dashboard_view, name='portal-dashboard'),
    path('portal/profile/', user_profile_view, name='portal-profile'),

    # Custom Professional Admin Management Console
    path('portal/admin/', admin_console_view, name='admin-console'),
    path('portal/admin/toggle-user/<uuid:user_id>/', admin_toggle_user_status_view, name='admin-toggle-user-status'),
    path('portal/admin/change-role/<uuid:user_id>/', admin_change_user_role_view, name='admin-change-role'),
    path('portal/admin/create-user/', admin_create_user_view, name='admin-create-user'),
    path('portal/admin/verify-farmer/<uuid:farmer_id>/', admin_verify_farmer_view, name='admin-verify-farmer'),

    # Milestone M2: DFAC Operational Cockpit & Map
    path('cockpit/', cockpit_view, name='cockpit'),
    path('cockpit/resolve-duplicate/<uuid:farmer_id>/', resolve_duplicate_view, name='cockpit-resolve-duplicate'),
    path('cockpit/upload-attendance/', cockpit_upload_attendance_view, name='cockpit-upload-attendance'),
    path('api/farms-geojson/', farms_geojson_view, name='farms-geojson'),
    
    # Milestone M2: Verifiable Credential Portal
    path('verify-certificate/', verify_certificate_view, name='verify-certificate'),
    path('verify-certificate/<str:code>/', verify_certificate_view, name='verify-certificate-detail'),

    # Milestone M3: Role-Scoped Portals (Lender & Buyer)
    path('portal/lender/', lender_portal_view, name='lender-portal'),
    path('portal/buyer/', buyer_portal_view, name='buyer-portal'),
    path('portal/buyer/confirm-match/<uuid:match_id>/', confirm_produce_match_portal, name='confirm-produce-match'),
    path('portal/buyer/auto-match/<uuid:demand_id>/', trigger_auto_match_portal, name='trigger-auto-match'),

    # Milestone M4: Field Operations & Inspection Cockpit
    path('portal/fieldops/', field_officer_portal_view, name='fieldops-portal'),
    path('portal/fieldops/log-visit/', fieldops_log_visit_portal, name='fieldops-log-visit-portal'),
    path('portal/fieldops/report-incident/', fieldops_report_incident_portal, name='fieldops-report-incident-portal'),
    path('portal/fieldops/auto-dispatch/', fieldops_auto_dispatch_portal, name='fieldops-auto-dispatch-portal'),

    # Milestone M5: Trainer & Smallholder Farmer Portals
    path('portal/trainer/', trainer_portal_view, name='trainer-portal'),
    path('portal/trainer/schedule/', trainer_schedule_session_portal, name='trainer-schedule-session'),
    path('portal/trainer/issue-cert/', trainer_issue_certificate_portal, name='trainer-issue-cert'),
    path('portal/farmer/', farmer_portal_view, name='farmer-portal'),

    # Milestone M6: USSD & SMS Simulator
    path('portal/ussd-simulator/', ussd_simulator_view, name='ussd-simulator'),

    # Milestone M7: Donor Reporting & Inputs Management
    path('portal/reporting/', donor_reporting_portal_view, name='reporting-portal'),
    path('portal/inputs/', inputs_portal_view, name='inputs-portal'),
    path('portal/inputs/confirm-delivery/<uuid:order_id>/', confirm_input_delivery_portal, name='portal-confirm-input-delivery'),

    # Mobile Field Operations APK Download
    path('download/apk/', download_apk_view, name='download-apk'),
]
