from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    RequestOTPView,
    VerifyOTPView,
    CurrentUserView,
    ConsentRecordViewSet
)

router = DefaultRouter()
router.register('consent', ConsentRecordViewSet, basename='consent')

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('otp/request/', RequestOTPView.as_view(), name='otp_request'),
    path('otp/verify/', VerifyOTPView.as_view(), name='otp_verify'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
    path('', include(router.urls)),
]
