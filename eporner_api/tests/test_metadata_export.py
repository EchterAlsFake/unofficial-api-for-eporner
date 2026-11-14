import unittest

from eporner_api.api import Video


class MetadataExportTests(unittest.TestCase):
    def test_keeps_actor_names_without_fetching_profiles(self):
        content = '''<script type="application/ld+json">{"@type":"VideoObject","name":"Example",
          "actor":[{"name":"Example Actor","url":"https://eporner.com/pornstar/example/"}]}</script>'''
        fields = Video._extract_html(content)
        self.assertEqual(fields["performers"][0]["name"], "Example Actor")
        self.assertEqual(fields["performers"][0]["url"], fields["authors_urls"][0])
