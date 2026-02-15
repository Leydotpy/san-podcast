def get_default_title(instance):
    title = instance.podcast.title
    episode_number = (instance.podcast.get_episodes().count()) + 1
    return f"{title} - (Episode {episode_number})"
