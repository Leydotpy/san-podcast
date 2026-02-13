# pylint: disable=W0201

from django.apps import apps
from django.urls import path

from core.application import AppConfig


class Api(AppConfig):
    name = "api"

    namespace = "api"
    def ready(self):
        from api.views import api_root
        self.rest = apps.get_app_config("rest")
        # self.graphiql = apps.get_app_config("graphql")
        self._api_root = api_root

    def get_urls(self):
        urls = [
            path("", self._api_root, name="api-root"),
            path("rest/", self.rest.urls, name="rest"),
            # path("graphql/", self.graphiql.urls, name="graphql")
        ]
        return urls
# http://localhost:8000/api/rest/web/profile/queue/