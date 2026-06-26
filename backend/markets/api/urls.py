from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BacktestView, MarketAssetViewSet

router = DefaultRouter()
router.register("market-assets", MarketAssetViewSet, basename="market-asset")

urlpatterns = [
    *router.urls,
    path("backtest/", BacktestView.as_view(), name="backtest"),
]
