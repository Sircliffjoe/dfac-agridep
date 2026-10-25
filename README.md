# DFAC AgriDEP (Agricultural Data Ecosystem Platform)

**Doctor Fish Agricultural Consult (DFAC)**  
*“Connecting Farmers, Data, Finance and Markets.”*

[![Python](https://img.shields.io/badge/Python-3.14.4-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-6.1.2-green.svg)](https://djangoproject.com)
[![DRF](https://img.shields.io/badge/DRF-3.18.3-red.svg)](https://django-rest-framework.org)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-3.0.3-orange.svg)](/api/v1/schema/swagger-ui/)
[![Dokku](https://img.shields.io/badge/Deploy-Dokku-purple.svg)](https://dokku.com)

---

## 1. Overview & Operational Context

DFAC AgriDEP is a multi-stakeholder agricultural data and decision platform designed for rural deployment across the Niger Delta (Delta, Bayelsa, and Rivers states). It captures data once at the point of activity and routes it to farmers, field officers, trainers, lenders, buyers/off-takers, and DFAC management.

The platform is **decision-workflow driven**: it automatically answers operational imperatives such as which farms are ready for harvest off-take, which loans require early intervention, and which farms are overdue for extension visits.

### Core Non-Negotiable Tenets
1. **Three Identity Anchors:** `Farmer`, `Farm`, and `Buyer` are the single source of truth across all modules.
2. **Offline-First Field Capture:** Supports both **KoboToolbox / ODK Collect** form webhooks and a dedicated **Flutter + Drift SQLite** offline mobile client with delta sync.
3. **Strict RBAC & Tenant Row-Level Scoping:** Scoped database querysets prevent cross-tenant data leakage; commercial buyers see anonymized producer data prior to deal confirmation.
4. **Nigeria Data Protection Act (NDPA 2023) Compliance:** Encrypted National Identification Numbers (NIN) and phone numbers at rest, explicit consent tracking (`ConsentRecord`), and immutable audit logging (`AuditEvent`).
5. **Dokku VPS Ready:** Native support for zero-downtime Dokku deployment via `Procfile`, `app.json`, and `CHECKS`.

---

## 2. Technology Stack

* **Language & Runtime:** Python 3.14.4
* **Backend Framework:** Django 6.1.2 + Django REST Framework 3.18.3
* **API Documentation:** drf-spectacular (OpenAPI 3.0.3 Schema, Swagger UI, ReDoc)
* **Databases:** PostgreSQL 16 + PostGIS (Production / Dokku) / SQLite (Zero-config local development)
* **Asynchronous Jobs:** Celery + Celery Beat + Redis
* **Mobile Field App:** Flutter (Android-first) + Drift (SQLite) with outbox queue and delta sync (`/api/v1/sync/push/`, `/api/v1/sync/pull/`)
* **Security & Encryption:** Fernet symmetric cryptography for sensitive PII; SHA-256 deterministic hashes for duplicate detection

---

## 3. Local Development Quickstart

### Prerequisites
* Python 3.14.4+
* Virtual environment (`.venv`)

### Setup & Run
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Apply database migrations
make migrate

# 3. Seed realistic Nigerian demo data (Delta, Bayelsa, Rivers)
make seed

# 4. Run automated test suite
make test

# 5. Start development server
make run
```
Access the server at `http://localhost:8000`:
* **Healthcheck:** `http://localhost:8000/api/v1/health/`
* **Swagger UI:** `http://localhost:8000/api/v1/schema/swagger-ui/`
* **ReDoc:** `http://localhost:8000/api/v1/schema/redoc/`
* **Django Admin:** `http://localhost:8000/admin/` (User: `admin` / Password: `admin12345`)

---

## 4. End-to-End Milestone Demonstrations

### Milestone M0 & M1 Demo
```bash
python docs/demo/m0_m1_demo.py
```
Exercises:
1. System health and OpenAPI schema generation.
2. Field Officer JWT authentication.
3. Smallholder farmer registration with encrypted NIN and address.
4. Duplicate-farmer detection engine (exact phone and fuzzy name matching).
5. Pond biometric logging triggering decision rule **RULE-01** (harvest-ready transition).
6. Remote KoboToolbox / ODK form webhook ingestion.
7. Flutter Drift SQLite batch push and delta pull.
8. Commercial Buyer RBAC field-level data masking.
9. NDPA 2023 immutable audit logging.

### Milestone M2 Demo (Capacity Building, Verifiable Credentials & Operational Cockpit)
```bash
python docs/demo/m2_demo.py
```
Exercises:
1. Trainer authentication and approved curriculum inspection.
2. Bulk paper attendance sheet ingestion (CSV / Excel format) with smallholder resolution.
3. Practical competency assessments and automated qualification scoring.
4. Security-grade accreditation certificate generation (ReportLab A4 landscape PDF + dynamic QR code).
5. Public and partner credential verification (`/verify-certificate/<token>/`).
6. DFAC Management Operational Cockpit (`/cockpit/`) and PostGIS regional farm map.

---

## 5. Deploying to a VPS via Dokku

AgriDEP is structured for deployment to Dokku on any Ubuntu VPS.

### Dokku Deployment Steps
```bash
# On your VPS:
dokku apps:create dfac-agridep

# Provision managed PostgreSQL and Redis plugins:
dokku postgres:create agridep-db
dokku postgres:link agridep-db dfac-agridep

dokku redis:create agridep-redis
dokku redis:link agridep-redis dfac-agridep

# Set production environment variables:
dokku config:set dfac-agridep \
  DJANGO_SETTINGS_MODULE=agridep.config.settings.production \
  DJANGO_SECRET_KEY='your-production-secret-key-32-chars-min' \
  DJANGO_ALLOWED_HOSTS='agridep.yourdomain.ng,vps-ip' \
  FIELD_ENCRYPTION_KEY='your-base64-fernet-key' \
  SECURE_SSL_REDIRECT=True

# From your local repository:
git remote add dokku dokku@your-vps-ip:dfac-agridep
git push dokku master
```
Dokku automatically executes:
1. `Procfile` web and worker processes (`gunicorn`, `celery worker`, `celery beat`).
2. `app.json` postdeploy script: `python manage.py migrate --noinput` and `collectstatic`.
3. `CHECKS` zero-downtime healthcheck against `/api/v1/health/`.

---

## 6. Seed Accounts & Credentials

| Role | Username | Password | Purpose |
|---|---|---|---|
| **DFAC Admin** | `admin` | `admin12345` | Management cockpit and full ecosystem administration |
| **Field Officer** | `officer_delta` | `password123` | Farm inspections, farmer registration, pond logs |
| **Trainer** | `trainer_john` | `password123` | Capacity building and attendance scoring |
| **Lender** | `lender_bank` | `password123` | Agricultural credit monitoring |
| **Buyer** | `buyer_aggregator` | `password123` | Commercial off-take matching |
