from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from .models import Entitlement, Subscription

# Try to get a raw Redis connection via django-redis if available for set ops.
try:
    from django_redis import get_redis_connection

    _have_redis = True
except Exception:
    _have_redis = False

CACHE_TTL_SECONDS = getattr(settings, "ACCESS_CACHE_TTL_SECONDS", 30)
USER_CACHE_SET_PREFIX = getattr(settings, "USER_ACCESS_KEY_SET_PREFIX", "user_access_keys")  # redis set name prefix


def get_user_highest_active_subscription(user):
    # if not user or not getattr(user, "is_authenticated", False):
    #     return None
    # uses SubscriptionManager.active_for_user
    return (Subscription.objects.active_for_user(user).
            select_related("membership__plan").
            order_by('-membership__plan__tier').first())


def has_entitlement(user, content_obj):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    ct = ContentType.objects.get_for_model(type(content_obj))
    now = timezone.now()
    return Entitlement.objects.filter(
        user=user,
        content_type=ct,
        object_id=str(getattr(content_obj, "pk", getattr(content_obj, "id", None))),
        revoked=False
    ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)).exists()


class AccessService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, cache_backend=cache, ttl=CACHE_TTL_SECONDS):
        self.cache = cache_backend
        self.ttl = ttl
        # redis connection if available
        self._redis = get_redis_connection("default") if _have_redis else None

    # canonical cache key pattern: access:user:<pk|anon>:<app_label.model>:<obj_pk>
    @staticmethod
    def _cache_key(user, obj):
        user_key = f"user:{user.pk}" if (user and getattr(user, "is_authenticated", False)) else "user:anon"
        return f"access:{user_key}:{obj._meta.label_lower}:{obj.pk}"

    @staticmethod
    def _user_set_key(user):
        return f"{USER_CACHE_SET_PREFIX}:{user.pk}"

    def _register_cache_key_for_user(self, user, key):
        if not user or not getattr(user, "is_authenticated", False):
            # do not register anon keys
            return
        if self._redis:
            try:
                self._redis.sadd(self._user_set_key(user), key)
            except Exception:
                pass
        else:
            # Fallback: keep a small list in Django cache (less ideal, but works)
            list_key = f"{self._user_set_key(user)}:list"
            existing = self.cache.get(list_key) or []
            if key not in existing:
                existing.append(key)
                # keep for a short time longer than entries TTL
                self.cache.set(list_key, existing, timeout=self.ttl * 3)

    def _get_keys_for_user(self, user):
        if not user or not getattr(user, "is_authenticated", False):
            return []
        if self._redis:
            try:
                keys = self._redis.smembers(self._user_set_key(user))
                # smembers returns bytes -> decode to str
                return [k.decode() if isinstance(k, bytes) else k for k in keys]
            except Exception:
                return []
        else:
            list_key = f"{self._user_set_key(user)}:list"
            return self.cache.get(list_key) or []

    def _clear_keys_for_user(self, user):
        keys = self._get_keys_for_user(user)
        for k in keys:
            try:
                self.cache.delete(k)
            except Exception:
                pass
        # also delete the index (set/list)
        if self._redis:
            try:
                self._redis.delete(self._user_set_key(user))
            except Exception:
                pass
        else:
            list_key = f"{self._user_set_key(user)}:list"
            self.cache.delete(list_key)

    # Public API
    def has_access(self, user, obj):
        key = self._cache_key(user, obj)
        val = self.cache.get(key)
        if val is not None:
            return bool(val)

        result = self._compute_has_access(user, obj)
        # register and set cache
        # store boolean (1/0)
        self.cache.set(key, bool(result), timeout=self.ttl)
        # register key for user so we can invalidate later
        try:
            self._register_cache_key_for_user(user, key)
        except Exception:
            pass
        return result

    def invalidate_user_cache(self, user):
        """Clear all cached access results for a given user (use in signals)."""
        self._clear_keys_for_user(user)

    # You can expose more fine-grained invalidation if needed
    def invalidate_user_obj(self, user, obj):
        key = self._cache_key(user, obj)
        self.cache.delete(key)
        # Also remove it from the user's key set
        if self._redis:
            try:
                self._redis.srem(self._user_set_key(user), key)
            except Exception:
                pass
        else:
            list_key = f"{self._user_set_key(user)}:list"
            existing = self.cache.get(list_key) or []
            if key in existing:
                existing.remove(key)
                self.cache.set(list_key, existing, timeout=self.ttl * 3)

    # -------------------------
    # Core access evaluation
    # -------------------------
    @staticmethod
    def _compute_has_access(user, obj):
        """
        Implement the same ordered checks we designed earlier:
          1. admin bypass
          2. Episode.availability for public/non-exclusive
          3. subscription plan fast-path (Episode.available_for(plan=...))
          4. plan-targeted entitlements -> treat as virtual plan
          5. object-level entitlements
          6. category -> plan fallback
        """
        now = timezone.now()

        # Avoid circular imports at module top
        from .models import Plan, Entitlement

        # 1. admin bypass
        if user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return True

        # 2. quick Episode public check
        # if isinstance(obj, Episode):
            # Episode.available_for(plan=None) returns True for public accessible episodes
        if obj.available_for(plan=None, now=now):
            return True

        # 3. subscription fast-path
        sub = get_user_highest_active_subscription(user)
        plan = None
        if sub:
            plan = sub.membership.plan
            # if isinstance(obj, Episode):
            if obj.available_for(plan=plan, now=now):
                return True
            # else:
            #     if plan.grants(*features):
            #         return True

        # 4. plan-targeted entitlements
        plan_ct = ContentType.objects.get_for_model(Plan)
        plan_ent_qs = Entitlement.objects.filter(
            user=user, content_type=plan_ct, revoked=False
        ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))

        for ent in plan_ent_qs.select_related("content_type"):
            p = ent.content_object
            if not p:
                continue
            #if isinstance(obj, Episode):
            if obj.available_for(plan=p, now=now):
                return True
            # else:
            #     if p.grants(*features):
            #         return True

        # 5. object-level entitlement
        obj_ct = ContentType.objects.get_for_model(type(obj))
        if has_entitlement(user, obj_ct):
            return True
        return False
