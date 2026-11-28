import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import netlis_search
import updater
from storage import BrowserStorage

class PrivacyRegressionTests(unittest.TestCase):
    def test_search_does_not_fall_back_when_tor_fails(self):
        with patch.object(netlis_search,'fetch_text_via_socks5',side_effect=OSError('offline')),patch.object(netlis_search,'urlopen') as direct:
            self.assertEqual(netlis_search.run_netlis_metasearch('test',use_tor=True)['results'],[])
            direct.assert_not_called()

    def test_feed_does_not_fall_back_when_tor_fails(self):
        with patch.object(updater,'fetch_text_via_socks5',side_effect=OSError('offline')),patch.object(updater,'urlopen') as direct:
            with self.assertRaises(OSError):updater._download_feed_text('https://example.org')
            direct.assert_not_called()

    def test_history_cannot_recover_deleted_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=BrowserStorage(Path(tmp));store.add_history('a','https://example.org/a');store.add_history('b','https://example.org/b')
            self.assertTrue(store.history_path.with_suffix('.json.bak').exists())
            store.clear_history()
            self.assertEqual(BrowserStorage(Path(tmp)).history,[])
            self.assertFalse(store.history_path.with_suffix('.json.bak').exists())

    def test_app_update_blocks_direct_network_in_tor_mode(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'urlopen') as direct,patch.object(updater.subprocess,'run') as process:
            self.assertFalse(updater.apply_app_update(Path(tmp))[0])
            direct.assert_not_called();process.assert_not_called()
