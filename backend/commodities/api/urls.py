from rest_framework.routers import DefaultRouter

from .views import (
    CommodityViewSet,
    CountryViewSet,
    EventViewSet,
    ProductViewSet,
    SectorViewSet,
)

router = DefaultRouter()
router.register("commodities", CommodityViewSet, basename="commodity")
router.register("countries", CountryViewSet, basename="country")
router.register("sectors", SectorViewSet, basename="sector")
router.register("products", ProductViewSet, basename="product")
router.register("events", EventViewSet, basename="event")

urlpatterns = router.urls
