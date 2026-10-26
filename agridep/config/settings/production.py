import os
from .base import *

DEBUG = False

# Allowed hosts for Dokku & domain routing
ALLOWED_HOSTS = [
    'agridep.eventro.africa',
    '169.58.122.43',
    'localhost',
    '127.0.0.1',
    '.eventro.africa',
] + [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]

# CSRF Trusted Origins for forms & authentication
CSRF_TRUSTED_ORIGINS = [
    'https://agridep.eventro.africa',
    'http://agridep.eventro.africa',
] + [o.strip() for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

CORS_ALLOWED_ORIGINS = [
    'https://agridep.eventro.africa',
] + [c.strip() for c in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if c.strip()]

# Security headers behind Dokku / Nginx reverse proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1')
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
