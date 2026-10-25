from django.urls import path, include
from rest_framework.routers import DefaultRouter
from agridep.apps.finance.views import (
    LenderViewSet,
    LoanRecordViewSet,
    LoanTrancheViewSet,
    RepaymentViewSet,
    RiskFlagViewSet,
)

router = DefaultRouter()
router.register(r'lenders', LenderViewSet, basename='lender')
router.register(r'loans', LoanRecordViewSet, basename='loan-record')
router.register(r'tranches', LoanTrancheViewSet, basename='loan-tranche')
router.register(r'repayments', RepaymentViewSet, basename='repayment')
router.register(r'risk-flags', RiskFlagViewSet, basename='risk-flag')

urlpatterns = [
    path('', include(router.urls)),
]
