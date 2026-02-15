# my_dataset.py
import tensorflow as tf
import tensorflow_datasets as tfds

from apps.posts.podcasts.models import Podcast, Episode

def get_podcasts():
    podcasts = Podcast.objects.all()
    return [
        {field.name: getattr(podcast, field.name)} for podcast in podcasts.objects.all()
        for fields in podcast._meta.get_fields() for field in fields
    ]


class PodcastDataset(tfds.core.GeneratorBasedBuilder):
    """DatasetBuilder for articles dataset."""
    VERSION = tfds.core.Version('1.0.0')

    def _info(self):
        return tfds.core.DatasetInfo(
            builder=self,
            description="Dataset of posts with title and content",
            features=tfds.features.FeaturesDict({
                'title': tfds.features.Text(),
                'teams': tfds.features.Text(),
                'players': tfds.features.Text(),
                'matches': tfds.features.Text(),
                'season': tfds.features.Text(),
                'parent': tfds.features.Text(),
            }),
            supervised_keys=('title', 'teams', 'players', 'matches', 'season', 'parent'),
            citation=r"""@podcast{podcastdataset, title={Podcast Dataset}, year={2024}}""",
        )

    def _split_generators(self, dl_manager):
        return {
            'train': self._generate_examples(),
        }

    def _generate_examples(self):
        """Yields examples."""
        articles = get_podcasts()
        for i, article in enumerate(articles):
            yield i, {
                'title': article['title'],
                'content': article['content'],
            }
