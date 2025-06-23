import os
import pickle
import json
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SettingsManager:
    """Модуль для управления настройками торгового бота"""
    
    def __init__(self, settings_file='bot_settings.pkl'):
        self.settings_file = settings_file
        self.settings = self.load_default_settings()
        
        # Колбэки для обновления UI
        self.on_settings_updated = None
        # self.on_error = None # Replaced by logger
        # self.on_log = None # Replaced by logger
        
        # Загрузка настроек после инициализации колбэков
        self.load_settings()
    
    def load_default_settings(self):
        """Загрузка настроек по умолчанию"""
        return {
            'general': {
                'theme': 'dark',
                'auto_trading': False,
                'auto_update': True,
                'update_interval': 30,  # секунды
                'log_level': 'INFO'
            },
            'trading': {
                'symbol': 'BTCUSDT',
                'interval': '1h',
                'mode': 'simulation',  # simulation или real
                'leverage': 10,
                'risk_percent': 1.0,
                'take_profit_percent': 2.0,
                'stop_loss_percent': 1.0,
                'trailing_stop': False,
                'trailing_percent': 0.5,
                'auto_trading': False
            },
            'chart': {
                'show_volume': True,
                'show_orderbook': True,
                'show_density_zones': True,
                'show_signals': True,
                'candlestick_style': 'classic',  # classic или hollow
                'theme_colors': {
                    'background': '#1c1c1c',
                    'text': '#e0e0e0',
                    'grid': '#333333',
                    'up_candle': '#26a69a',
                    'down_candle': '#ef5350',
                    'volume_up': '#26a69a80',
                    'volume_down': '#ef535080',
                    'signal_buy': '#26a69a',
                    'signal_sell': '#ef5350'
                }
            },
            'ml': {
                'enabled': True,
                'auto_train': True,
                'train_interval': 60,  # минуты
                'model_type': 'GradientBoosting',  # RandomForest, GradientBoosting
                'confidence_threshold': 0.6
            },
            'api': {
                'api_key': '',
                'api_secret': '',
                'testnet': True
            },
            'ui': {
                'font_size': 10,
                'show_toolbar': True,
                'show_status_bar': True,
                'layout': 'default'
            },
            'last_update': datetime.now().timestamp()
        }
    
    def load_settings(self):
        """Загрузка настроек из файла"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'rb') as f:
                    loaded_settings = pickle.load(f)
                
                # Обновление настроек по умолчанию загруженными
                self.update_nested_dict(self.settings, loaded_settings)
                
                logger.info(f"Настройки загружены из {self.settings_file}")
                
                # Вызов колбэка обновления настроек
                if self.on_settings_updated:
                    self.on_settings_updated(self.settings)
                
                return True
            else:
                logger.warning(f"Файл настроек не найден. Используются настройки по умолчанию.")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}", exc_info=True)
            return False
    
    def save_settings(self):
        """Сохранение настроек в файл"""
        try:
            # Обновление времени последнего обновления
            self.settings['last_update'] = datetime.now().timestamp()
            
            with open(self.settings_file, 'wb') as f:
                pickle.dump(self.settings, f)
            
            logger.info(f"Настройки сохранены в {self.settings_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}", exc_info=True)
            return False
    
    def update_settings(self, category, settings_dict):
        """Обновление настроек определенной категории"""
        try:
            if category in self.settings:
                # Обновление настроек
                self.update_nested_dict(self.settings[category], settings_dict)
                
                # Сохранение настроек
                self.save_settings()
                
                # Вызов колбэка обновления настроек
                if self.on_settings_updated:
                    self.on_settings_updated(self.settings)
                
                return True
            else:
                logger.error(f"Категория настроек '{category}' не найдена")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка обновления настроек: {e}", exc_info=True)
            return False
    
    def get_settings(self, category=None):
        """Получение настроек"""
        if category:
            return self.settings.get(category, {})
        return self.settings
    
    def export_settings(self, file_path):
        """Экспорт настроек в JSON файл"""
        try:
            # Преобразование datetime в строку для JSON
            settings_copy = self.deep_copy_settings(self.settings)
            settings_copy['last_update'] = datetime.fromtimestamp(settings_copy['last_update']).strftime('%Y-%m-%d %H:%M:%S')
            
            with open(file_path, 'w') as f:
                json.dump(settings_copy, f, indent=4)
            
            logger.info(f"Настройки экспортированы в {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка экспорта настроек: {e}", exc_info=True)
            return False
    
    def import_settings(self, file_path):
        """Импорт настроек из JSON файла"""
        try:
            with open(file_path, 'r') as f:
                imported_settings = json.load(f)
            
            # Преобразование строки даты в timestamp
            if 'last_update' in imported_settings and isinstance(imported_settings['last_update'], str):
                try:
                    dt = datetime.strptime(imported_settings['last_update'], '%Y-%m-%d %H:%M:%S')
                    imported_settings['last_update'] = dt.timestamp()
                except:
                    imported_settings['last_update'] = datetime.now().timestamp()
            
            # Обновление настроек
            self.update_nested_dict(self.settings, imported_settings)
            
            # Сохранение настроек
            self.save_settings()
            
            logger.info(f"Настройки импортированы из {file_path}")
            
            # Вызов колбэка обновления настроек
            if self.on_settings_updated:
                self.on_settings_updated(self.settings)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка импорта настроек: {e}", exc_info=True)
            return False
    
    def reset_settings(self, category=None):
        """Сброс настроек до значений по умолчанию"""
        try:
            default_settings = self.load_default_settings()
            
            if category:
                if category in self.settings and category in default_settings:
                    self.settings[category] = default_settings[category]
                else:
                    logger.error(f"Категория настроек '{category}' не найдена")
                    return False
            else:
                self.settings = default_settings
            
            # Сохранение настроек
            self.save_settings()
            
            logger.info(f"Настройки сброшены до значений по умолчанию")
            
            # Вызов колбэка обновления настроек
            if self.on_settings_updated:
                self.on_settings_updated(self.settings)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сброса настроек: {e}", exc_info=True)
            return False
    
    def update_nested_dict(self, d, u):
        """Рекурсивное обновление вложенного словаря"""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self.update_nested_dict(d[k], v)
            else:
                d[k] = v
    
    def deep_copy_settings(self, settings):
        """Глубокое копирование настроек"""
        if isinstance(settings, dict):
            return {k: self.deep_copy_settings(v) for k, v in settings.items()}
        elif isinstance(settings, list):
            return [self.deep_copy_settings(v) for v in settings]
        else:
            return settings