import json

from django.conf import settings

from apps.posts.podcasts.models import Podcast


# Podcast = apps.get_model("podcasts.Podcast")


class UserHistoryManager:
    cookie_name = settings.RECENTLY_VIEWED_PODCAST_COOKIE_NAME
    cookie_kwargs = {
        "max_age": settings.RECENTLY_VIEWED_COOKIE_LIFETIME,
        "secure": settings.RECENTLY_VIEWED_COOKIE_SECURE,
        "httponly": True,
        "samesite": settings.SESSION_COOKIE_SAMESITE,
    }
    max_podcasts = settings.RECENTLY_VIEWED_ITEMS

    @classmethod
    def get(cls, request):
        """
        Return a list of recently viewed products
        """
        ids = cls.extract(request)

        # Reordering as the ID order gets messed up in the query
        podcast_dict = Podcast.objects.browsable().in_bulk(ids)
        ids.reverse()

        return [
            podcast_dict[podcast_id] for podcast_id in ids if podcast_id in podcast_dict
        ]

    @classmethod
    def extract(cls, request, response=None):
        """
        Extract the IDs of products in the history cookie
        """
        ids = []
        if cls.cookie_name in request.COOKIES:
            try:
                ids = json.loads(request.COOKIES[cls.cookie_name])
            except ValueError:
                # This can occur if something messes up the cookie
                if response:
                    response.delete_cookie(cls.cookie_name)
            else:
                # Badly written web crawlers send garbage in double quotes
                if not isinstance(ids, list):
                    ids = []
        return ids

    @classmethod
    def add(cls, ids, new_id):
        """
        Add a new product ID to the list of product IDs
        """
        if new_id in ids:
            ids.remove(new_id)
        ids.append(new_id)
        if len(ids) > cls.max_podcasts:
            ids = ids[len(ids) - cls.max_podcasts:]
        return ids

    @classmethod
    def update(cls, podcast, request, response):
        """
        Updates the cookies that store the recently viewed products
        removing possible duplicates.
        """
        ids = cls.extract(request, response)
        updated_ids = cls.add(ids, podcast.id)
        response.set_cookie(
            cls.cookie_name, json.dumps(updated_ids), **cls.cookie_kwargs
        )
        print("response cookies after set in signals ==>", response.cookies)
