from django.contrib import admin

# Register your models here.
from .models import Discussion, Reply


class ReplyInline(admin.TabularInline):
    model = Reply


class DiscussionAdmin(admin.ModelAdmin):
    inlines = [ReplyInline]

    class Meta:
        model = Discussion


admin.site.register(Discussion, DiscussionAdmin)
