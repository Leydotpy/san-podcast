from django.contrib import admin

from .models import UserCategoryAffinity


class UserCategoryAffinityAdmin(admin.ModelAdmin):
    readonly_fields = ('user', 'category', 'score')
    list_display = ('id', 'user', 'category', 'score')
    list_filter = ('user', 'score', 'created')
    search_fields = ('user__username', 'category__name', 'category__tier__name')
    ordering = ('user__username', 'category__name', 'category__tier__name')

    class Meta:
        model = UserCategoryAffinity


admin.site.register(UserCategoryAffinity, UserCategoryAffinityAdmin)