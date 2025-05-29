import numpy as np
import pandas as pd
import time
import threading
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from collections import deque

class MLManager:
    """Модуль для управления ML-моделью торгового бота"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.accuracy = 0.0
        self.is_training = False
        self.last_train_time = 0
        self.train_interval = 60.0  # Минимальный интервал между обучениями (сек)
        
        # История предсказаний
        self.predictions_history = deque(maxlen=100)
        
        # Колбэки для обновления UI
        self.on_training_complete = None
        self.on_error = None
        self.on_log = None
    
    def prepare_features(self, df, for_prediction=False):
        """Подготовка признаков для модели.
        Если for_prediction is True, возвращает только последний ряд признаков (X_last).
        Иначе, возвращает полный набор X и y для обучения.
        """
        if df is None or len(df) < 30:
            return None if for_prediction else (None, None)
        
        try:
            # Создание копии данных
            data = df.copy()
            
            # Технические индикаторы
            # SMA - простые скользящие средние
            data['sma_5'] = data['close'].rolling(window=5).mean()
            data['sma_10'] = data['close'].rolling(window=10).mean()
            data['sma_20'] = data['close'].rolling(window=20).mean()
            
            # EMA - экспоненциальные скользящие средние
            data['ema_5'] = data['close'].ewm(span=5, adjust=False).mean()
            data['ema_10'] = data['close'].ewm(span=10, adjust=False).mean()
            data['ema_20'] = data['close'].ewm(span=20, adjust=False).mean()
            
            # Bollinger Bands
            data['bb_middle'] = data['close'].rolling(window=20).mean()
            data['bb_std'] = data['close'].rolling(window=20).std()
            data['bb_upper'] = data['bb_middle'] + 2 * data['bb_std']
            data['bb_lower'] = data['bb_middle'] - 2 * data['bb_std']
            data['bb_width'] = (data['bb_upper'] - data['bb_lower']) / data['bb_middle']
            
            # RSI - индекс относительной силы
            delta = data['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
            rs = gain / loss
            data['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD - схождение/расхождение скользящих средних
            data['ema_12'] = data['close'].ewm(span=12, adjust=False).mean()
            data['ema_26'] = data['close'].ewm(span=26, adjust=False).mean()
            data['macd'] = data['ema_12'] - data['ema_26']
            data['macd_signal'] = data['macd'].ewm(span=9, adjust=False).mean()
            data['macd_hist'] = data['macd'] - data['macd_signal']
            
            # Объемные индикаторы
            data['volume_sma_5'] = data['volume'].rolling(window=5).mean()
            data['volume_ratio'] = data['volume'] / data['volume_sma_5']
            
            # Свечные паттерны
            data['body_size'] = abs(data['close'] - data['open']) / (data['high'] - data['low'])
            data['upper_shadow'] = (data['high'] - data[['open', 'close']].max(axis=1)) / (data['high'] - data['low'])
            data['lower_shadow'] = (data[['open', 'close']].min(axis=1) - data['low']) / (data['high'] - data['low'])
            
            # Ценовые изменения
            data['price_change'] = data['close'].pct_change()
            data['price_change_1'] = data['close'].pct_change(periods=1)
            data['price_change_2'] = data['close'].pct_change(periods=2)
            data['price_change_5'] = data['close'].pct_change(periods=5)
            data['price_change_10'] = data['close'].pct_change(periods=10)
            
            # Волатильность
            data['volatility'] = data['close'].rolling(window=10).std() / data['close'].rolling(window=10).mean()
            
            # Целевая переменная: 1 если цена выросла через N периодов, иначе 0
            n_periods = 3
            data['target'] = (data['close'].shift(-n_periods) > data['close']).astype(int)
            
            # Удаление строк с NaN
            data = data.dropna()
            
            if len(data) < 10:
                return None, None
            
            # Выбор признаков
            features = ['sma_5', 'sma_10', 'sma_20', 'ema_5', 'ema_10', 'ema_20',
                      'bb_width', 'rsi', 'macd', 'macd_signal', 'macd_hist',
                      'volume_ratio', 'body_size', 'upper_shadow', 'lower_shadow',
                      'price_change', 'price_change_1', 'price_change_2', 'price_change_5',
                      'volatility']
            
            X = data[features].values
            
            if for_prediction:
                if len(X) == 0:
                    return None
                return X[-1:] # Возвращаем только последний ряд признаков для предсказания
            
            y = data['target'].values
            return X, y
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка подготовки признаков: {e}")
            return None if for_prediction else (None, None)
    
    def train_model(self, df):
        """Обучение ML-модели"""
        # Проверка на слишком частые обучения
        current_time = time.time()
        if (current_time - self.last_train_time) < self.train_interval:
            return False
        
        if self.is_training:
            return False
        
        # Запуск обучения в отдельном потоке
        self.is_training = True
        threading.Thread(target=self.train_async, args=(df,), daemon=True).start()
        return True
    
    def train_async(self, df):
        """Асинхронное обучение модели"""
        try:
            X, y = self.prepare_features(df)
            
            if X is None or y is None or len(X) < 20:
                self.is_training = False
                return
            
            # Разделение на обучающую и тестовую выборки
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Нормализация данных
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Создание и обучение модели
            model = GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)
            model.fit(X_train_scaled, y_train)
            
            # Оценка точности
            y_pred = model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            # Обновление модели и точности
            self.model = model
            self.accuracy = accuracy
            self.last_train_time = time.time()
            
            if self.on_log:
                self.on_log(f"Модель обучена. Точность: {accuracy:.2f}", "SUCCESS")
            
            # Вызов колбэка завершения обучения
            if self.on_training_complete:
                self.on_training_complete(accuracy)
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обучения модели: {e}")
        finally:
            self.is_training = False
    
    def predict(self, features_last_row, current_timestamp=None, current_price=None):
        """Прогнозирование сигналов торговли на основе уже подготовленной последней строки признаков."""
        if self.model is None:
            if self.on_log: self.on_log("Модель не обучена, предсказание невозможно.", "WARNING")
            return None
        if features_last_row is None:
            if self.on_log: self.on_log("Нет признаков для предсказания.", "WARNING")
            return None
        
        # Ensure features_last_row is 2D for scaler and model
        if features_last_row.ndim == 1:
            features_last_row = features_last_row.reshape(1, -1)
        
        try:
            X_last_scaled = self.scaler.transform(features_last_row)
            
            # Прогнозирование
            prediction = self.model.predict(X_last_scaled)[0]
            probability = self.model.predict_proba(X_last_scaled)[0]
            
            # Сохранение предсказания в истории
            if current_timestamp and current_price:
                self.predictions_history.append({
                    'timestamp': current_timestamp,
                    'prediction': prediction,
                    'probability': probability.max(),
                    'price': current_price
                })
            
            return {
                'signal': 'BUY' if prediction == 1 else 'SELL',
                'probability': probability.max(),
                'confidence': 'HIGH' if probability.max() > 0.7 else 'MEDIUM' if probability.max() > 0.6 else 'LOW'
            }
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка прогнозирования: {e}")
            return None
    
    def get_model_info(self):
        """Получение информации о модели"""
        if self.model is None:
            return "Модель не обучена"
        
        return {
            'type': type(self.model).__name__,
            'accuracy': self.accuracy,
            'features': self.model.feature_importances_ if hasattr(self.model, 'feature_importances_') else None,
            'last_train': self.last_train_time
        }