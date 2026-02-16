from django.contrib import admin
from apps.region.models import Region, Country


class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "slug", "timestamp")
    search_fields = ("name", "code")
    search_help_text = "Search by name, code..."

    class Meta:
        model = Region
        fields = ("name", "slug", "image", "code")


class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "slug", "timestamp")
    search_fields = ("name", "code")
    search_help_text = "Search by name, code..."

    class Meta:
        model = Country
        fields = ("name", "slug", "image", "code")


admin.site.register(Region, RegionAdmin)
admin.site.register(Country, CountryAdmin)