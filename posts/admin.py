from django.contrib import admin

# Register your models here.
from .models import Post, PostReaction

admin.site.register(Post)
admin.site.register(PostReaction)
