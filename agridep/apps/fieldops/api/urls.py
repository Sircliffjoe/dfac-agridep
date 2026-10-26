from django.urls import path, include
from rest_framework.routers import DefaultRouter
from agridep.apps.fieldops.api.views import (
    FarmVisitViewSet,
    InspectionViewSet,
    InspectionPhotoViewSet,
    IncidentReportViewSet,
    VisitAssignmentViewSet,
    PriorityQueueAPIView,
)

router = DefaultRouter()
router.register('visits', FarmVisitViewSet, basename='fieldops-visit')
router.register('inspections', InspectionViewSet, basename='fieldops-inspection')
router.register('photos', InspectionPhotoViewSet, basename='fieldops-photo')
router.register('incidents', IncidentReportViewSet, basename='fieldops-incident')
router.register('assignments', VisitAssignmentViewSet, basename='fieldops-assignment')

urlpatterns = [
    path('priority-queue/', PriorityQueueAPIView.as_view(), name='fieldops-priority-queue'),
    path('', include(router.urls)),
]
