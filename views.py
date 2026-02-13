import collections

from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


def PUBLIC_APIS(request, format):
    return [
        ("auto", reverse("auto", request=request, format=format)),
        ("handpicked", reverse("handpicked", request=request, format=format)),
        ("promotions", reverse("promotions", request=request, format=format)),
        ("profile", reverse("profile", request=request, format=format)),
        ("queue", reverse("queue-detail", request=request, format=format)),
        ("playlists", reverse("user-playlist", request=request, format=format)),
        ("react", reverse("react-to-model", request=request, format=format)),
        ("subscription", reverse("user-subscription", request=request, format=format)),
        ("featured playlists", reverse("featured-playlist", request=request, format=format)),
    ]

@api_view(["GET"])
def api_root(request, format=None, *args, **kwargs):
    apis = collections.OrderedDict(PUBLIC_APIS(request, format))
    return Response(apis)
