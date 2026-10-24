from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EnterpriseTypeViewSet, CohortViewSet, FarmerViewSet, FarmViewSet, BuyerViewSet

router = DefaultRouter()
router.register('enterprises', EnterpriseTypeViewSet, basename='enterprise')
router.register('cohorts', CohortViewSet, basename='cohort')
router.register('farmers', FarmerViewSet, basename='farmer')
router.register('farms', FarmViewSet, basename='farm')
router.register('buyers', BuyerViewSet, basename='buyer')

urlpatterns = [
    path('', include(router.urls)),
]
