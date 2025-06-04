import unittest
import os
import tempfile
import json
import pickle
from unittest.mock import patch, MagicMock
from datetime import datetime

from settings_manager import SettingsManager


class TestSettingsManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a temporary file for testing
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pkl')
        self.temp_file.close()
        self.temp_file_path = self.temp_file.name
        
        # Create SettingsManager instance with temporary file
        self.sm = SettingsManager(settings_file=self.temp_file_path)
        
        # Mock callbacks to prevent errors
        self.sm.on_settings_updated = MagicMock()
        self.sm.on_error = MagicMock()
        self.sm.on_log = MagicMock()
    
    def tearDown(self):
        """Clean up after each test method."""
        # Remove temporary file
        if os.path.exists(self.temp_file_path):
            os.unlink(self.temp_file_path)
    
    def test_load_default_settings(self):
        """Test loading default settings structure."""
        default_settings = self.sm.load_default_settings()
        
        # Check that all required categories exist
        required_categories = ['general', 'trading', 'chart', 'ml', 'api', 'ui']
        for category in required_categories:
            self.assertIn(category, default_settings)
        
        # Check some specific default values
        self.assertEqual(default_settings['general']['theme'], 'dark')
        self.assertEqual(default_settings['trading']['symbol'], 'BTCUSDT')
        self.assertEqual(default_settings['trading']['mode'], 'simulation')
        self.assertTrue(default_settings['chart']['show_volume'])
        self.assertTrue(default_settings['ml']['enabled'])
        
        # Check that last_update is a timestamp
        self.assertIsInstance(default_settings['last_update'], float)
    
    def test_save_and_load_settings(self):
        """Test saving and loading settings from file."""
        # Modify some settings
        original_symbol = self.sm.settings['trading']['symbol']
        self.sm.settings['trading']['symbol'] = 'ETHUSDT'
        self.sm.settings['general']['theme'] = 'light'
        
        # Save settings
        result = self.sm.save_settings()
        self.assertTrue(result)
        
        # Create new instance to load settings
        sm2 = SettingsManager(settings_file=self.temp_file_path)
        sm2.on_log = MagicMock()
        sm2.on_settings_updated = MagicMock()
        
        # Check that settings were loaded correctly
        self.assertEqual(sm2.settings['trading']['symbol'], 'ETHUSDT')
        self.assertEqual(sm2.settings['general']['theme'], 'light')
    
    def test_load_settings_file_not_exists(self):
        """Test loading settings when file doesn't exist."""
        # Remove the file
        os.unlink(self.temp_file_path)
        
        # Create new instance
        sm = SettingsManager(settings_file=self.temp_file_path)
        sm.on_log = MagicMock()
        
        # Should return False and use default settings
        result = sm.load_settings()
        self.assertFalse(result)
        sm.on_log.assert_called()
    
    def test_update_settings(self):
        """Test updating settings for a specific category."""
        # Update trading settings
        new_trading_settings = {
            'symbol': 'ETHUSDT',
            'leverage': 20,
            'risk_percent': 2.0
        }
        
        result = self.sm.update_settings('trading', new_trading_settings)
        self.assertTrue(result)
        
        # Check that settings were updated
        self.assertEqual(self.sm.settings['trading']['symbol'], 'ETHUSDT')
        self.assertEqual(self.sm.settings['trading']['leverage'], 20)
        self.assertEqual(self.sm.settings['trading']['risk_percent'], 2.0)
        
        # Check that other settings remain unchanged
        self.assertEqual(self.sm.settings['trading']['mode'], 'simulation')
        
        # Check that callbacks were called
        self.sm.on_settings_updated.assert_called()
    
    def test_update_settings_invalid_category(self):
        """Test updating settings with invalid category."""
        result = self.sm.update_settings('invalid_category', {'test': 'value'})
        self.assertFalse(result)
        self.sm.on_error.assert_called()
    
    def test_get_settings(self):
        """Test getting settings."""
        # Get all settings
        all_settings = self.sm.get_settings()
        self.assertIsInstance(all_settings, dict)
        self.assertIn('trading', all_settings)
        
        # Get specific category
        trading_settings = self.sm.get_settings('trading')
        self.assertIsInstance(trading_settings, dict)
        self.assertIn('symbol', trading_settings)
        
        # Get non-existent category
        empty_settings = self.sm.get_settings('non_existent')
        self.assertEqual(empty_settings, {})
    
    def test_export_settings(self):
        """Test exporting settings to JSON."""
        # Create temporary JSON file
        json_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        json_file.close()
        json_file_path = json_file.name
        
        try:
            # Export settings
            result = self.sm.export_settings(json_file_path)
            self.assertTrue(result)
            
            # Check that file was created and contains valid JSON
            self.assertTrue(os.path.exists(json_file_path))
            
            with open(json_file_path, 'r') as f:
                exported_data = json.load(f)
            
            # Check that exported data contains expected categories
            self.assertIn('trading', exported_data)
            self.assertIn('general', exported_data)
            
            # Check that last_update was converted to string
            self.assertIsInstance(exported_data['last_update'], str)
            
        finally:
            # Clean up
            if os.path.exists(json_file_path):
                os.unlink(json_file_path)
    
    def test_import_settings(self):
        """Test importing settings from JSON."""
        # Create test JSON data
        test_settings = {
            'trading': {
                'symbol': 'ADAUSDT',
                'leverage': 15
            },
            'general': {
                'theme': 'light'
            },
            'last_update': '2023-01-01 12:00:00'
        }
        
        # Create temporary JSON file
        json_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w')
        json.dump(test_settings, json_file, indent=4)
        json_file.close()
        json_file_path = json_file.name
        
        try:
            # Import settings
            result = self.sm.import_settings(json_file_path)
            self.assertTrue(result)
            
            # Check that settings were imported
            self.assertEqual(self.sm.settings['trading']['symbol'], 'ADAUSDT')
            self.assertEqual(self.sm.settings['trading']['leverage'], 15)
            self.assertEqual(self.sm.settings['general']['theme'], 'light')
            
            # Check that last_update was converted to timestamp
            self.assertIsInstance(self.sm.settings['last_update'], float)
            
            # Check that callbacks were called
            self.sm.on_settings_updated.assert_called()
            
        finally:
            # Clean up
            if os.path.exists(json_file_path):
                os.unlink(json_file_path)
    
    def test_reset_settings(self):
        """Test resetting settings to defaults."""
        # Modify some settings
        self.sm.settings['trading']['symbol'] = 'ETHUSDT'
        self.sm.settings['general']['theme'] = 'light'
        
        # Reset all settings
        result = self.sm.reset_settings()
        self.assertTrue(result)
        
        # Check that settings were reset to defaults
        self.assertEqual(self.sm.settings['trading']['symbol'], 'BTCUSDT')
        self.assertEqual(self.sm.settings['general']['theme'], 'dark')
        
        # Check that callbacks were called
        self.sm.on_settings_updated.assert_called()
    
    def test_reset_settings_specific_category(self):
        """Test resetting settings for a specific category."""
        # Modify trading settings
        self.sm.settings['trading']['symbol'] = 'ETHUSDT'
        self.sm.settings['trading']['leverage'] = 20
        original_theme = self.sm.settings['general']['theme']
        
        # Reset only trading settings
        result = self.sm.reset_settings('trading')
        self.assertTrue(result)
        
        # Check that trading settings were reset
        self.assertEqual(self.sm.settings['trading']['symbol'], 'BTCUSDT')
        self.assertEqual(self.sm.settings['trading']['leverage'], 10)
        
        # Check that other settings remain unchanged
        self.assertEqual(self.sm.settings['general']['theme'], original_theme)
    
    def test_reset_settings_invalid_category(self):
        """Test resetting settings with invalid category."""
        result = self.sm.reset_settings('invalid_category')
        self.assertFalse(result)
        self.sm.on_error.assert_called()
    
    def test_update_nested_dict(self):
        """Test the nested dictionary update utility function."""
        original = {
            'level1': {
                'level2': {
                    'key1': 'value1',
                    'key2': 'value2'
                },
                'key3': 'value3'
            },
            'key4': 'value4'
        }
        
        update = {
            'level1': {
                'level2': {
                    'key1': 'new_value1',
                    'key_new': 'new_value'
                },
                'key_new2': 'new_value2'
            },
            'key_new3': 'new_value3'
        }
        
        self.sm.update_nested_dict(original, update)
        
        # Check that nested values were updated
        self.assertEqual(original['level1']['level2']['key1'], 'new_value1')
        self.assertEqual(original['level1']['level2']['key2'], 'value2')  # unchanged
        self.assertEqual(original['level1']['level2']['key_new'], 'new_value')
        self.assertEqual(original['level1']['key3'], 'value3')  # unchanged
        self.assertEqual(original['level1']['key_new2'], 'new_value2')
        self.assertEqual(original['key4'], 'value4')  # unchanged
        self.assertEqual(original['key_new3'], 'new_value3')
    
    def test_deep_copy_settings(self):
        """Test the deep copy utility function."""
        original = {
            'dict': {'nested': 'value'},
            'list': [1, 2, {'nested_in_list': 'value'}],
            'string': 'test',
            'number': 42
        }
        
        copied = self.sm.deep_copy_settings(original)
        
        # Check that copy is equal but not the same object
        self.assertEqual(copied, original)
        self.assertIsNot(copied, original)
        self.assertIsNot(copied['dict'], original['dict'])
        self.assertIsNot(copied['list'], original['list'])
        self.assertIsNot(copied['list'][2], original['list'][2])
        
        # Modify copy and ensure original is unchanged
        copied['dict']['nested'] = 'modified'
        self.assertEqual(original['dict']['nested'], 'value')
    
    @patch('pickle.load')
    def test_load_settings_pickle_error(self, mock_pickle_load):
        """Test handling of pickle loading errors."""
        # Create a file that exists but causes pickle error
        with open(self.temp_file_path, 'w') as f:
            f.write('invalid pickle data')
        
        mock_pickle_load.side_effect = Exception("Pickle error")
        
        result = self.sm.load_settings()
        self.assertFalse(result)
        self.sm.on_error.assert_called()
    
    @patch('pickle.dump')
    def test_save_settings_pickle_error(self, mock_pickle_dump):
        """Test handling of pickle saving errors."""
        mock_pickle_dump.side_effect = Exception("Pickle save error")
        
        result = self.sm.save_settings()
        self.assertFalse(result)
        self.sm.on_error.assert_called()


if __name__ == '__main__':
    unittest.main()