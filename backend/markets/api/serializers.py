from rest_framework import serializers

from markets.models import MarketAsset


class MarketAssetSerializer(serializers.ModelSerializer):
    asset_class_display = serializers.CharField(source="get_asset_class_display", read_only=True)
    ref = serializers.SerializerMethodField()

    class Meta:
        model = MarketAsset
        fields = ["id", "ref", "code", "name", "asset_class", "asset_class_display", "currency"]

    def get_ref(self, obj) -> str:
        return f"asset:{obj.code}"
