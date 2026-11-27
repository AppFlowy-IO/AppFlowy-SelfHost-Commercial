"""AI Meeting's YouTube import is served by AppFlowy Web, although its path starts with /api."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
NGINX = (ROOT / 'docker/nginx/nginx.conf').read_text()
ROUTE = '/api/youtube-audio'


class YoutubeImportRouteTests(unittest.TestCase):
    def test_bundled_nginx_sends_the_import_to_web(self):
        # An exact location wins over the /api prefix, which sends every other /api request to Cloud.
        blocks = re.findall(r'location = ' + re.escape(ROUTE) + r' \{([^}]*)\}', NGINX)
        self.assertEqual(len(blocks), 1)
        self.assertIn('proxy_pass $appflowy_web_backend;', blocks[0])

    def test_no_other_location_sends_the_import_elsewhere(self):
        self.assertNotRegex(NGINX, r'location (\^~ |~\*? )?' + re.escape(ROUTE))


if __name__ == '__main__':
    unittest.main()
