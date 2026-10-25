from django.urls import path, include
from rest_framework.routers import DefaultRouter
from agridep.apps.training.views import (
    TrainingProgrammeViewSet,
    TrainingSessionViewSet,
    AttendanceViewSet,
    AssessmentViewSet,
    CertificateViewSet,
)

router = DefaultRouter()
router.register(r'programmes', TrainingProgrammeViewSet, basename='training-programme')
router.register(r'sessions', TrainingSessionViewSet, basename='training-session')
router.register(r'attendance', AttendanceViewSet, basename='training-attendance')
router.register(r'assessments', AssessmentViewSet, basename='training-assessment')
router.register(r'certificates', CertificateViewSet, basename='training-certificate')

urlpatterns = [
    path('', include(router.urls)),
]
