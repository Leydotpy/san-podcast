from django.utils.timezone import now

now = now()


def image_upload_location(instance, filename):
    klass, name, time = instance.__class__.__name__, instance.name, now.strftime('%H%M%S.%f')
    return "{0}/{1}/{1}.{2}.{3}".format(klass, name, time, filename)
