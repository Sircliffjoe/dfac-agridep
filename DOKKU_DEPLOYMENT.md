# Dokku Deployment Guide for DFAC AgriDEP™

This guide outlines the step-by-step procedure to deploy the **DFAC AgriDEP™** platform to your Dokku PaaS host with zero downtime, automated database migrations, WhiteNoise static asset serving, Celery background workers, and SSL encryption.

---

## 1. Prerequisites on Dokku Server

Ensure the official Dokku Postgres and Redis plugins are installed on your Dokku server:

```bash
# Install Postgres and Redis plugins (run as root on Dokku server)
dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres
dokku plugin:install https://github.com/dokku/dokku-redis.git redis
dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git letsencrypt
```

---

## 2. Create the Application & Services

Run the following commands on your Dokku host:

```bash
# 1. Create the application
dokku apps:create dfac-agridep

# 2. Provision and link PostgreSQL (PostGIS enabled if needed)
dokku postgres:create dfac-agridep-db
dokku postgres:link dfac-agridep-db dfac-agridep

# 3. Provision and link Redis (for Celery & caching)
dokku redis:create dfac-agridep-redis
dokku redis:link dfac-agridep-redis dfac-agridep

# 4. Set persistent storage mount for uploaded media (certificates, farmer photos)
dokku storage:ensure-directory dfac-agridep-media
dokku storage:mount dfac-agridep /var/lib/dokku/data/storage/dfac-agridep-media:/app/media
```

---

## 3. Configure Environment Variables

Set the production environment variables:

```bash
dokku config:set dfac-agridep \
  DJANGO_SETTINGS_MODULE="agridep.config.settings.production" \
  DJANGO_SECRET_KEY="$(openssl rand -hex 32)" \
  DJANGO_ALLOWED_HOSTS="agridep.yourdomain.com,dfac-agridep.yourserver.com" \
  DJANGO_CSRF_TRUSTED_ORIGINS="https://agridep.yourdomain.com" \
  CORS_ALLOWED_ORIGINS="https://agridep.yourdomain.com" \
  SECURE_SSL_REDIRECT="True" \
  SESSION_COOKIE_SECURE="True" \
  CSRF_COOKIE_SECURE="True"
```

*(Optional API keys for SMS and USSD):*
```bash
dokku config:set dfac-agridep \
  AFRICAS_TALKING_USERNAME="your-username" \
  AFRICAS_TALKING_API_KEY="your-api-key"
```

---

## 4. Deploying from Local Repository

Add the Dokku remote to your local machine repository and deploy:

```bash
# Add Dokku remote (replace dokku.yourdomain.com with your Dokku server IP or host)
git remote add dokku dokku@dokku.yourdomain.com:dfac-agridep

# Deploy via git push
git push dokku main
```

### What Happens Automatically on Deploy:
1. **Buildpack & Dependencies:** Python 3.14 buildpack installs packages from `requirements.txt`.
2. **Post-deploy (`app.json`):** Dokku automatically runs:
   - `python manage.py migrate --noinput`
   - `python manage.py collectstatic --noinput`
3. **WhiteNoise Static Engine:** Static files are compressed and fingerprinted in `staticfiles/` and served directly with long-lived cache headers.
4. **Zero-Downtime Health Check (`CHECKS`):** Dokku tests `/api/v1/health/` up to 6 times (waiting 5 seconds between checks). Traffic only switches over after a 200 OK response.

---

## 5. Scale Process Workers (Celery & Beat)

Scale your web dyno and Celery background workers according to `Procfile`:

```bash
# Scale 1 web instance, 1 Celery worker, 1 Celery beat scheduler
dokku ps:scale dfac-agridep web=1 worker=1 beat=1
```

---

## 6. Configure Custom Domain & SSL (Let's Encrypt)

```bash
# Add your custom domain
dokku domains:set dfac-agridep agridep.yourdomain.com

# Enable automated Let's Encrypt SSL certificates
dokku letsencrypt:set dfac-agridep email admin@yourdomain.com
dokku letsencrypt:enable dfac-agridep
dokku letsencrypt:auto-renew dfac-agridep
```

---

## 7. Initial Superuser & Demo Data

Create the administrative cockpit superuser:

```bash
# Run interactive createsuperuser inside the deployed container
dokku run dfac-agridep python manage.py createsuperuser

# (Optional) Seed realistic Niger Delta demo data
dokku run dfac-agridep python manage.py populate_demo_data
```

Your DFAC AgriDEP™ platform is now live!
