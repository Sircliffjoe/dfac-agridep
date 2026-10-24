from django.urls import path
from .views import (
    home_view,
    about_view,
    value_chains_view,
    solutions_view,
    impact_view,
    contact_view,
    portal_login_view,
)

urlpatterns = [
    path('', home_view, name='home'),
    path('about/', about_view, name='about'),
    path('value-chains/', value_chains_view, name='value-chains'),
    path('solutions/', solutions_view, name='solutions'),
    path('impact/', impact_view, name='impact'),
    path('contact/', contact_view, name='contact'),
    path('login/', portal_login_view, name='portal-login'),
]
