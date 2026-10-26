from django.urls import path
from agridep.apps.reporting.api.views import (
    DonorIndicatorsAPIView,
    DonorExcelExportAPIView,
    DonorPDFExportAPIView,
)

urlpatterns = [
    path('indicators/', DonorIndicatorsAPIView.as_view(), name='reporting-indicators'),
    path('export/excel/', DonorExcelExportAPIView.as_view(), name='reporting-export-excel'),
    path('export/pdf/', DonorPDFExportAPIView.as_view(), name='reporting-export-pdf'),
]
