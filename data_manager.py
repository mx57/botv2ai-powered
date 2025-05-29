import pandas as pd
import numpy as np
import requests
import time
import json
import threading
import websocket
from datetime import datetime, timedelta
from collections import deque

class DataManager:
    """Модуль для управления данными торгового бота"""
    
    def __init__(self, symbol='BTCUSDT', interval='1h'):
        self.symbol = symbol
        self.interval = interval
        self.df = None
        self.density_zones = []
        self.orderbook_data = {'bids': [], 'asks': []}
        self.ws = None
        self.price_history = deque(maxlen=1000)  # История цен для анализа
        self.volume_history = deque(maxlen=1000)  # История объемов
        
        # Оптимизация производительности
        self.last_data_update = 0
        self.last_density_calc = 0
        self.data_update_interval = 2.0  # Минимальный интервал между обновлениями (сек)
        
        # Колбэки для обновления UI
        self.on_data_updated = None
        self.on_orderbook_updated = None
        self.on_error = None
        self.on_log = None
    
    def set_symbol_interval(self, symbol, interval):
        """Установка символа и интервала"""
        if symbol != self.symbol or interval != self.interval:
            self.symbol = symbol
            self.interval = interval
            self.restart_websocket()
    
    def get_kline_data(self, limit=500):
        """Получение исторических данных свечей"""
        try:
            # Проверка на слишком частые обновления
            current_time = time.time()
            if (current_time - self.last_data_update) < self.data_update_interval:
                return self.df
            
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            # Преобразование данных в DataFrame
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'quote_asset_volume', 'number_of_trades',
                                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            
            # Преобразование типов данных
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_columns] = df[numeric_columns].astype(float)
            
            # Преобразование временной метки
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Проверка на изменения данных
            if self.df is not None and len(df) > 0 and len(self.df) > 0:
                if len(df) == len(self.df) and abs(df.iloc[-1]['close'] - self.df.iloc[-1]['close']) < 0.0001:
                    return self.df  # Данные практически не изменились
            
            self.df = df
            self.last_data_update = current_time
            
            # Обновление истории цен и объемов
            if len(df) > 0:
                self.price_history.append(df.iloc[-1]['close'])
                self.volume_history.append(df.iloc[-1]['volume'])
            
            # Расчет зон плотности (реже)
            if (current_time - self.last_density_calc) > 10.0:
                self.calculate_density_zones()
                self.last_density_calc = current_time
            
            # Вызов колбэка обновления данных
            if self.on_data_updated:
                self.on_data_updated(self.df, self.density_zones if hasattr(self, 'density_zones') else [])
            
            if self.on_log:
                self.on_log(f"Данные {self.symbol} ({self.interval}) обновлены", "INFO")
                
            return self.df
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка получения данных: {e}")
            return None
    
    def calculate_density_zones(self, volume_threshold=0.7):
        """Расчет зон плотности на основе объема и цены"""
        if self.df is None or len(self.df) < 20:
            return []
        
        try:
            df = self.df.copy()
            
            # Нормализация объема
            df['volume_norm'] = df['volume'] / df['volume'].max()
            
            # Выбор свечей с высоким объемом
            high_volume = df[df['volume_norm'] > volume_threshold]
            
            if len(high_volume) == 0:
                return []
            
            # Кластеризация цен
            price_points = []
            for _, row in high_volume.iterrows():
                # Добавляем точки цен с весом объема
                price_points.extend([row['low']] * int(row['volume_norm'] * 10))
                price_points.extend([row['high']] * int(row['volume_norm'] * 10))
                price_points.extend([row['open']] * int(row['volume_norm'] * 15))
                price_points.extend([row['close']] * int(row['volume_norm'] * 15))
            
            if not price_points:
                return []
            
            # Находим кластеры цен
            price_array = np.array(price_points).reshape(-1, 1)
            
            # Простая кластеризация на основе расстояния
            clusters = []
            current_price = price_array[0][0]
            cluster_prices = [current_price]
            
            price_range = df['high'].max() - df['low'].min()
            distance_threshold = price_range * 0.01  # 1% от диапазона цен
            
            for price in price_array[1:]:
                if abs(price[0] - current_price) < distance_threshold:
                    cluster_prices.append(price[0])
                else:
                    if len(cluster_prices) > 5:  # Минимальный размер кластера
                        clusters.append(cluster_prices)
                    cluster_prices = [price[0]]
                    current_price = price[0]
            
            if len(cluster_prices) > 5:
                clusters.append(cluster_prices)
            
            # Создание зон плотности
            zones = []
            current_price = df.iloc[-1]['close']
            
            for i, cluster in enumerate(clusters):
                center = np.mean(cluster)
                width = np.std(cluster) * 2  # 2 стандартных отклонения
                
                # Определение типа зоны (поддержка или сопротивление)
                zone_type = 'resistance' if center > current_price else 'support'
                
                # Сила зоны на основе количества точек и объема
                strength = len(cluster) / len(price_points)
                
                zones.append({
                    'center': center,
                    'width': max(width, price_range * 0.005),  # Минимальная ширина
                    'type': zone_type,
                    'strength': strength,
                    'touches': sum(1 for _, row in df.iterrows() 
                                 if abs(row['low'] - center) < width or 
                                    abs(row['high'] - center) < width)
                })
            
            # Сортировка зон по силе
            zones.sort(key=lambda x: x['strength'], reverse=True)
            
            # Ограничение количества зон
            self.density_zones = zones[:10]
            
            if self.on_log:
                self.on_log(f"Найдено {len(self.density_zones)} зон плотности", "INFO")
                
            return self.density_zones
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка расчета зон плотности: {e}")
            return []
    
    def on_websocket_message(self, ws, message):
        """Обработка сообщений WebSocket"""
        try:
            # Ограничение частоты обработки сообщений
            current_time = time.time()
            if hasattr(self, 'last_ws_update') and (current_time - self.last_ws_update) < 0.2:
                return
            
            data = json.loads(message)
            
            if 'bids' in data and 'asks' in data:
                self.orderbook_data = {
                    'bids': data['bids'][:20],
                    'asks': data['asks'][:20]
                }
                
                self.last_ws_update = current_time
                
                # Вызов колбэка обновления стакана
                if self.on_orderbook_updated:
                    self.on_orderbook_updated(self.orderbook_data)
                
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обработки WebSocket: {e}")
    
    def on_websocket_error(self, ws, error):
        """Обработка ошибок WebSocket"""
        if self.on_error:
            self.on_error(f"WebSocket ошибка: {error}")
    
    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработка закрытия WebSocket"""
        if self.on_log:
            self.on_log("WebSocket соединение закрыто", "WARNING")
        # Переподключение через 5 секунд
        threading.Timer(5.0, self.start_websocket).start()
    
    def start_websocket(self):
        """Запуск WebSocket для стакана заявок"""
        try:
            if self.ws:
                self.ws.close()
            
            symbol = self.symbol.lower()
            ws_url = f"wss://stream.binance.com:9443/ws/{symbol}@depth20@100ms"
            
            self.ws = websocket.WebSocketApp(ws_url,
                                           on_message=self.on_websocket_message,
                                           on_error=self.on_websocket_error,
                                           on_close=self.on_websocket_close)
            
            # Запуск в отдельном потоке
            ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            ws_thread.start()
            
            if self.on_log:
                self.on_log("WebSocket подключен", "SUCCESS")
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка запуска WebSocket: {e}")
    
    def restart_websocket(self):
        """Перезапуск WebSocket соединения"""
        if self.ws:
            self.ws.close()
        self.start_websocket()
    
    def stop_websocket(self):
        """Остановка WebSocket соединения"""
        try:
            if hasattr(self, 'ws') and self.ws:
                self.ws.close()
                self.ws = None
                if self.on_log:
                    self.on_log("WebSocket соединение закрыто", "INFO")
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка при остановке WebSocket: {e}")
    
    def stop(self):
        """Остановка всех процессов"""
        if self.ws:
            self.ws.close()
            self.ws = None