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

        self.profile_cache = {} # Cache for intra-candle volume profiles
    
    def _interval_to_milliseconds(self, interval_str):
        """Конвертирует строку интервала (например, '1m', '1h', '1d') в миллисекунды."""
        multipliers = {
            'm': 60 * 1000,
            'h': 60 * 60 * 1000,
            'd': 24 * 60 * 60 * 1000,
            'w': 7 * 24 * 60 * 60 * 1000,
            # Месяц ('M') обрабатывается отдельно из-за переменной длительности,
            # но для API Binance обычно не используется в таком контексте для startTime/endTime дельт.
            # Для простоты, если понадобится 'M', можно будет доработать или использовать для грубых оценок.
        }
        
        try:
            unit = interval_str[-1]
            value = int(interval_str[:-1])
            if unit in multipliers:
                return value * multipliers[unit]
            else: # Предполагаем, что это секунды, если нет суффикса, или неизвестный суффикс
                return int(interval_str) * 1000 
        except ValueError: # Если не удалось преобразовать числовую часть
            if self.on_error:
                self.on_error(f"Не удалось распознать интервал: {interval_str}")
            return None # Или значение по умолчанию, например, для 1 минуты

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

    def _fetch_klines_by_range(self, symbol, interval, startTime_ms, endTime_ms, limit=1000):
        """Внутренний метод для загрузки свечей за определенный период."""
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': startTime_ms,
                'endTime': endTime_ms, # Binance endTime is inclusive
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10) # 10 секунд таймаут
            response.raise_for_status() # Вызовет исключение для HTTP ошибок 4xx/5xx
            data = response.json()
            
            if not data:
                return pd.DataFrame() # Возвращаем пустой DataFrame, если нет данных

            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'quote_asset_volume', 'number_of_trades',
                                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_columns] = df[numeric_columns].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            # df.set_index('timestamp', inplace=True) # Индекс не нужен для этой функции, вернем с timestamp колонкой
            return df
            
        except requests.exceptions.RequestException as e:
            if self.on_error:
                self.on_error(f"Ошибка сети при загрузке свечей для профиля: {e}")
            return pd.DataFrame()
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обработки данных свечей для профиля: {e}")
            return pd.DataFrame()

    def get_intra_candle_volume_profile(self, symbol, main_candle_timestamp, main_candle_interval, 
                                        main_candle_high, main_candle_low, 
                                        profile_granularity_interval='1m', num_price_bins=20):
        """
        Получает и рассчитывает профиль объема внутри указанной основной свечи.
        main_candle_timestamp: Время начала основной свечи (в миллисекундах).
        """
        cache_key = (symbol, main_candle_timestamp, main_candle_interval, 
                     main_candle_high, main_candle_low, 
                     profile_granularity_interval, num_price_bins)
        
        if cache_key in self.profile_cache:
            if self.on_log:
                self.on_log(f"Профиль для {symbol} @ {main_candle_timestamp} из кэша.", "DEBUG")
            return self.profile_cache[cache_key]

        if self.on_log:
            self.on_log(f"Расчет профиля для {symbol} @ {main_candle_timestamp} ({main_candle_interval}). Гранулярность: {profile_granularity_interval}", "INFO")

        main_candle_duration_ms = self._interval_to_milliseconds(main_candle_interval)
        if main_candle_duration_ms is None:
            return [] # Ошибка конвертации интервала

        # Binance endTime для klines является инклюзивным.
        # startTime также инклюзивный.
        main_candle_end_ms = main_candle_timestamp + main_candle_duration_ms - 1 

        finer_klines_df = self._fetch_klines_by_range(symbol, profile_granularity_interval, 
                                                      main_candle_timestamp, main_candle_end_ms)

        if finer_klines_df is None or finer_klines_df.empty:
            if self.on_log:
                 self.on_log(f"Нет данных гранулярности {profile_granularity_interval} для {symbol} в диапазоне {main_candle_timestamp} - {main_candle_end_ms}", "WARNING")
            return []

        profile_bins = []
        if main_candle_high == main_candle_low: # Плоская свеча
            # Создаем один бин, охватывающий эту цену
            profile_bins.append({
                'price_level_start': main_candle_low,
                'price_level_end': main_candle_high,
                'total_volume': finer_klines_df['volume'].sum(),
                'buy_volume': finer_klines_df[finer_klines_df['close'] >= finer_klines_df['open']]['volume'].sum(),
                'sell_volume': finer_klines_df[finer_klines_df['close'] < finer_klines_df['open']]['volume'].sum(),
            })
        elif num_price_bins > 0 :
            bin_size = (main_candle_high - main_candle_low) / num_price_bins
            for i in range(num_price_bins):
                level_start = main_candle_low + (i * bin_size)
                level_end = main_candle_low + ((i + 1) * bin_size)
                # Для последнего бина убедимся, что он включает main_candle_high
                if i == num_price_bins - 1:
                    level_end = main_candle_high 
                profile_bins.append({
                    'price_level_start': level_start,
                    'price_level_end': level_end,
                    'total_volume': 0.0,
                    'buy_volume': 0.0,
                    'sell_volume': 0.0,
                })
            
            for _, row in finer_klines_df.iterrows():
                typical_price = (row['open'] + row['high'] + row['low'] + row['close']) / 4
                volume = row['volume']

                # Определяем, в какой бин попадает цена
                # Убедимся, что typical_price не выходит за пределы основного диапазона свечи
                # (хотя по логике не должен, если finer_klines в этом диапазоне)
                clamped_price = max(main_candle_low, min(typical_price, main_candle_high))

                if bin_size == 0: # Если все еще 0 после проверки main_candle_high == main_candle_low (маловероятно)
                     bin_index = 0 if num_price_bins == 1 else -1
                else:
                    bin_index = int((clamped_price - main_candle_low) / bin_size)
                
                # Коррекция для верхней границы: если цена равна main_candle_high, она должна попасть в последний бин
                if bin_index >= num_price_bins:
                    bin_index = num_price_bins - 1
                
                if 0 <= bin_index < num_price_bins:
                    profile_bins[bin_index]['total_volume'] += volume
                    if row['close'] >= row['open']: # Считаем как "buy" объем, если свеча зеленая/доджи
                        profile_bins[bin_index]['buy_volume'] += volume
                    else: # Считаем как "sell" объем, если свеча красная
                        profile_bins[bin_index]['sell_volume'] += volume
                # else: # На случай, если цена выходит за пределы (не должно случаться при правильном clamping)
                #     if self.on_log:
                #         self.on_log(f"Цена {typical_price} вышла за пределы бинов для {symbol}", "WARNING")
        
        self.profile_cache[cache_key] = profile_bins
        return profile_bins