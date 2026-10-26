from django.urls import path, include
from rest_framework.routers import DefaultRouter
from agridep.apps.market.views import (
    CommodityPriceViewSet,
    BuyerDemandViewSet,
    ProduceMatchViewSet,
    OfftakeTransactionViewSet,
    MarketIntelligenceAPIView,
)

router = DefaultRouter()
router.register(r'prices', CommodityPriceViewSet, basename='commodity-price')
router.register(r'demands', BuyerDemandViewSet, basename='buyer-demand')
router.register(r'matches', ProduceMatchViewSet, basename='produce-match')
router.register(r'offtake', OfftakeTransactionViewSet, basename='offtake-transaction')

urlpatterns = [
    path('intelligence/', MarketIntelligenceAPIView.as_view(), name='market-intelligence'),
    path('', include(router.urls)),
]
