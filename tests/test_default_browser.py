import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import default_browser as db

class DefaultBrowserTests(unittest.TestCase):
    def test_register_in_user_data_and_quote_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'Netlis Browser';root.mkdir();(root/'launch.sh').write_text('#!/bin/bash\n')
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(Path(tmp)/'data')}):
                desktop=db.register_desktop(root)
                self.assertEqual(desktop,Path(tmp)/'data/applications/netlis.desktop')
                text=desktop.read_text()
                self.assertIn(f'Exec=/bin/bash "{root}/launch.sh" %U',text)
                for kind in db.ASSOCIATIONS:self.assertIn(kind,text)

    def test_partial_associations_not_reported_as_success(self):
        with patch.object(db,'available',return_value=True),patch.object(db,'run_command',side_effect=[db.DESKTOP_ID,db.DESKTOP_ID,'other.desktop',db.DESKTOP_ID,db.DESKTOP_ID]):
            self.assertFalse(db.default_status()[0])

    def test_set_and_verify_all_associations(self):
        with patch.object(db,'available',return_value=True),patch.object(db,'register_desktop',return_value=Path('/tmp/apps/netlis.desktop')),patch.object(db.shutil,'which',return_value=None),patch.object(db,'run_command') as run,patch.object(db,'default_status',return_value=(True,'ok')):
            self.assertTrue(db.set_default_browser()[0])
            run.assert_any_call(['xdg-settings','set','default-web-browser',db.DESKTOP_ID])
            for kind in db.ASSOCIATIONS:run.assert_any_call(['xdg-mime','default',db.DESKTOP_ID,kind])

    def test_failure_is_visible(self):
        with patch.object(db,'available',return_value=True),patch.object(db,'register_desktop',side_effect=PermissionError('denied')):
            active,message=db.set_default_browser()
            self.assertFalse(active);self.assertIn('denied',message)

class WindowsDefaultBrowserTests(unittest.TestCase):
    def test_register_capabilities_without_changing_userchoice(self):
        with patch.object(db,'windows_launch_command',return_value='"C:\\Netlis App\\Netlis.exe"'),patch.object(db,'write_windows_value') as write:
            db.register_windows(Path('/test/Netlis'))
            entries=[call.args for call in write.call_args_list]
            self.assertIn((r'Software\RegisteredApplications','Netlis',db.WINDOWS_CAPABILITIES),entries)
            self.assertIn((db.WINDOWS_CAPABILITIES+r'\URLAssociations','https',db.WINDOWS_PROG_ID),entries)
            self.assertTrue(any(path==r'Software\Classes\.html\OpenWithProgids' for path,_,_ in entries))
            self.assertFalse(any('UserChoice' in path for path,_,_ in entries))
            self.assertTrue(any(value.endswith(' "%1"') for _,_,value in entries))

    def test_windows_settings_launch_is_not_reported_as_success(self):
        from types import SimpleNamespace
        with patch.object(db,'register_windows') as register,patch.object(db.sys,'getwindowsversion',return_value=SimpleNamespace(build=22631),create=True),patch.object(db.os,'startfile',create=True) as start:
            active,message=db.set_windows_default(Path('/test'))
            self.assertFalse(active)
            start.assert_called_once_with('ms-settings:defaultapps?registeredAppUser=Netlis')
            register.assert_called_once()

    def test_windows_10_uses_general_settings(self):
        from types import SimpleNamespace
        with patch.object(db,'register_windows'),patch.object(db.sys,'getwindowsversion',return_value=SimpleNamespace(build=19045),create=True),patch.object(db.os,'startfile',create=True) as start:
            db.set_windows_default(Path('/test'))
            start.assert_called_once_with('ms-settings:defaultapps')

    def test_executable_launch_command(self):
        with patch.object(db.sys,'frozen',True,create=True),patch.object(db.sys,'executable','C:/Program Files/Netlis/Netlis.exe'):
            self.assertEqual(db.windows_launch_command('/unused'),'"C:/Program Files/Netlis/Netlis.exe"')

if __name__=='__main__':unittest.main()
