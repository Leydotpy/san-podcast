from django.contrib import admin
from apps.posts.polls.models import Poll, Choice

admin.site.register(Poll)
admin.site.register(Choice)