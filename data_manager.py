import pandas as pd
import numpy as np
import requests
import time
import json
import threading
import websocket
from datetime import datetime, timedelta
from collections import deque
from profiling_utils import profile_me # Import the decorator

class DataManager:
    """Модуль для управления данными торгового бота"""
    
    def __init__(self, symbol='BTCUSDT', interval='1h'):
        self.symbol = symbol
        self.interval = interval
        self.df = None
        self.last_kline_timestamp = None # Для отслеживания времени последней свечи
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
            if self.on_log:
                self.on_log(f"Смена символа/интервала с {self.symbol}/{self.interval} на {symbol}/{interval}", "INFO")
            self.symbol = symbol
            self.interval = interval
            self.df = None # Сброс DataFrame при смене символа/интервала
            self.last_kline_timestamp = None # Сброс времени последней свечи
            self.density_zones = [] # Сброс зон плотности
            if self.on_data_updated: # Уведомляем UI об очистке данных
                # Передаем пустой DataFrame и пустые зоны, чтобы UI очистился
                self.on_data_updated(pd.DataFrame(), []) 
            self.restart_websocket()
    
    @profile_me(filename_prefix="dm_get_kline_data")
    def get_kline_data(self, limit=500):
        """Получение исторических данных свечей"""
        try:
            # Проверка на слишком частые обновления
            current_time = time.time()
            if (current_time - self.last_data_update) < self.data_update_interval and self.df is not None:
                # Если данные есть и интервал не прошел, возвращаем существующие данные
                # Однако, если это не первый запуск, можно попробовать получить только новые свечи
                if self.last_kline_timestamp is not None:
                    # Попытка получить только новые данные, если прошло достаточно времени для новой свечи
                    # Минимальный интервал для новой свечи (пример для минутных свечей)
                    min_candle_interval = pd.Timedelta(self.interval).total_seconds()
                    if (current_time - self.last_kline_timestamp.timestamp()/1000 > min_candle_interval * 0.9): # 0.9 для небольшого запаса
                        pass # Продолжаем для обновления дельты
                    else:
                        return self.df 
                else: # Если last_kline_timestamp еще не установлен (первый запуск)
                    return self.df


            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
            }

            if self.df is None or self.last_kline_timestamp is None:
                # Начальная загрузка или если нет сохраненного времени последней свечи
                params['limit'] = limit
                if self.on_log: self.on_log(f"Начальная загрузка {limit} свечей для {self.symbol} {self.interval}", "INFO")
            else:
                # Загрузка только новых свечей
                # Binance API startTime is inclusive, endTime is exclusive
                # Мы хотим получить свечи, начиная со следующей после last_kline_timestamp
                # last_kline_timestamp - это время открытия свечи, храним его в мс
                params['startTime'] = self.last_kline_timestamp + 1 # +1 мс, чтобы не включать предыдущую
                # params['limit'] = limit # Можно ограничить, но API вернет только новые
                if self.on_log: self.on_log(f"Запрос новых свечей для {self.symbol} {self.interval} с {pd.to_datetime(params['startTime'], unit='ms')}", "INFO")

            try:
                response = requests.get(url, params=params, timeout=10) # Добавлен таймаут
                response.raise_for_status() # Проверка на HTTP ошибки
                data = response.json()
                if self.on_log: self.on_log(f"API klines call successful for {self.symbol}, params: {params}. Got {len(data)} records.", "DEBUG")
            except requests.exceptions.HTTPError as http_err:
                if self.on_error: self.on_error(f"HTTP ошибка при получении klines: {http_err} - {response.text if 'response' in locals() and hasattr(response, 'text') else 'No response text'}")
                return self.df 
            except requests.exceptions.ConnectionError as conn_err:
                if self.on_error: self.on_error(f"Ошибка соединения при получении klines: {conn_err}")
                return self.df
            except requests.exceptions.Timeout as timeout_err:
                if self.on_error: self.on_error(f"Таймаут при получении klines: {timeout_err}")
                return self.df
            except requests.exceptions.RequestException as e: # More general requests exception
                if self.on_error:
                    self.on_error(f"Ошибка API запроса klines: {e}")
                return self.df # Возвращаем старые данные в случае ошибки сети/API

            if not data: # API call was successful but returned no data
                if self.on_log: self.on_log("Нет новых данных о свечах от API.", "DEBUG")
                self.last_data_update = current_time 
                return self.df

            # Преобразование данных в DataFrame
            new_df_from_api = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'quote_asset_volume', 'number_of_trades',
                                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            
            if new_df_from_api.empty:
                if self.on_log: self.on_log("API вернул пустой набор данных для свечей (после DataFrame).", "DEBUG")
                self.last_data_update = current_time
                return self.df

            # Преобразование типов данных
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            new_df_from_api[numeric_columns] = new_df_from_api[numeric_columns].astype(float)
            
            # Преобразование временной метки
            new_df_from_api['timestamp'] = pd.to_datetime(new_df_from_api['timestamp'], unit='ms')
            new_df_from_api.set_index('timestamp', inplace=True)

            if self.df is None or self.last_kline_timestamp is None:
                self.df = new_df_from_api
                if self.on_log: self.on_log(f"Инициализировано {len(self.df)} свечей.", "INFO")
            else:
                original_len = len(self.df)
                if not new_df_from_api.empty:
                    self.df = self.df[self.df.index < new_df_from_api.index[0]]
                
                self.df = pd.concat([self.df, new_df_from_api])
                self.df = self.df[~self.df.index.duplicated(keep='last')]
                self.df.sort_index(inplace=True)
                if self.on_log: self.on_log(f"Обновлено {len(self.df) - original_len} свечей. Всего: {len(self.df)}", "DEBUG")

            max_df_len = limit * 2 
            if len(self.df) > max_df_len:
               self.df = self.df.iloc[-max_df_len:]
               if self.on_log: self.on_log(f"Размер DataFrame ограничен до {len(self.df)} свечей.", "DEBUG")

            if not self.df.empty:
                new_kline_ts = int(self.df.index[-1].timestamp() * 1000)
                if self.last_kline_timestamp != new_kline_ts:
                    self.last_kline_timestamp = new_kline_ts
                    if self.on_log: self.on_log(f"Время последней свечи обновлено: {pd.to_datetime(self.last_kline_timestamp, unit='ms')}", "DEBUG")
            
            self.last_data_update = current_time
            
            if not self.df.empty:
                self.price_history.append(self.df.iloc[-1]['close'])
                self.volume_history.append(self.df.iloc[-1]['volume'])
            
            if (current_time - self.last_density_calc) > 10.0: # Density calc interval
                if self.on_log: self.on_log("Запуск расчета зон плотности...", "DEBUG")
                self.calculate_density_zones() # Assuming this method has its own error handling
                self.last_density_calc = current_time
            
            if self.on_data_updated:
                self.on_data_updated(self.df, self.density_zones if hasattr(self, 'density_zones') else [])
            
            if self.on_log:
                self.on_log(f"Данные {self.symbol} ({self.interval}) успешно обновлены. Записей: {len(self.df)}", "INFO")
                
            return self.df
            
        except Exception as e: # Catch-all for any other unexpected error during processing
            if self.on_error:
                self.on_error(f"Непредвиденная ошибка в get_kline_data: {e}")
            return self.df # Return existing df if any, otherwise it might be None
    
    @profile_me(filename_prefix="dm_calculate_density_zones")
    def calculate_density_zones(self, volume_threshold=0.7):
        """Расчет зон плотности на основе объема и цены"""
        if self.df is None or len(self.df) < 20:
            if self.on_log: self.on_log("Недостаточно данных для расчета зон плотности (DataFrame пуст или слишком мал).", "DEBUG")
            return [] # Возвращаем пустой список, если данных недостаточно
        
        try:
            if self.on_log: self.on_log(f"Начало расчета зон плотности. Всего свечей: {len(self.df)}", "DEBUG")
            df = self.df.copy()
            
            # Нормализация объема
            df['volume_norm'] = df['volume'] / df['volume'].max()
            
            # Выбор свечей с высоким объемом
            high_volume = df[df['volume_norm'] > volume_threshold]
            
            if len(high_volume) == 0:
                if self.on_log: self.on_log("Нет свечей с высоким объемом для расчета зон.", "DEBUG")
                return []
            
            # Кластеризация цен
            # Векторизованное создание price_points
            weights_low_high = (high_volume['volume_norm'] * 10).astype(int)
            weights_open_close = (high_volume['volume_norm'] * 15).astype(int)

            price_arrays = []
            if not high_volume.empty:
                price_arrays.append(np.repeat(high_volume['low'].values, weights_low_high))
                price_arrays.append(np.repeat(high_volume['high'].values, weights_low_high))
                price_arrays.append(np.repeat(high_volume['open'].values, weights_open_close))
                price_arrays.append(np.repeat(high_volume['close'].values, weights_open_close))
            
            if not price_arrays:
                if self.on_log: self.on_log("Не удалось создать массивы цен из свечей с высоким объемом.", "DEBUG")
                return []
            
            price_array = np.concatenate(price_arrays).reshape(-1, 1)
            
            if price_array.size == 0:
                if self.on_log: self.on_log("Массив цен для кластеризации пуст.", "DEBUG")
                return []
            
            # Простая кластеризация на основе расстояния
            price_array.sort(axis=0)

            clusters = []
            current_cluster_price_anchor = price_array[0][0]
            current_cluster_elements = [current_cluster_price_anchor]
            
            price_range = df['high'].max() - df['low'].min()
            if price_range == 0: 
                distance_threshold = 0.001 
            else:
                distance_threshold = price_range * 0.01
            
            min_cluster_size = 5

            for price_val in price_array[1:, 0]:
                if abs(price_val - current_cluster_price_anchor) < distance_threshold:
                    current_cluster_elements.append(price_val)
                else:
                    if len(current_cluster_elements) > min_cluster_size:
                        clusters.append(list(current_cluster_elements)) # Сохраняем копию
                    current_cluster_elements = [price_val]
                    current_cluster_price_anchor = price_val
            
            if len(current_cluster_elements) > min_cluster_size:
                clusters.append(list(current_cluster_elements))
            
            if not clusters:
                if self.on_log: self.on_log("Не найдено кластеров цен после фильтрации.", "DEBUG")
                return []

            # Создание зон плотности
            zones = []
            last_close_price = df.iloc[-1]['close']
            
            for cluster_element_list in clusters:
                center = np.mean(cluster_element_list)
                width = np.std(cluster_element_list) * 2 
                
                zone_type = 'resistance' if center > last_close_price else 'support'
                
                # Сила зоны на основе количества точек
                strength = len(cluster_element_list) / price_array.size if price_array.size > 0 else 0
                
                # Vectorized "touches" calculation
                zone_min_touch = center - width / 2
                zone_max_touch = center + width / 2

                low_touches = (df['low'] >= zone_min_touch) & (df['low'] <= zone_max_touch)
                high_touches = (df['high'] >= zone_min_touch) & (df['high'] <= zone_max_touch)
                passed_through = (df['low'] <= center) & (df['high'] >= center)
                
                calculated_touches = (low_touches | high_touches | passed_through).sum()
                
                zones.append({
                    'center': center,
                    'width': max(width, price_range * 0.005), 
                    'type': zone_type,
                    'strength': strength,
                    'touches': calculated_touches
                })
            
            zones.sort(key=lambda x: x['strength'], reverse=True)
            self.density_zones = zones[:10]
            
            if self.on_log:
                self.on_log(f"Расчет зон плотности завершен. Найдено {len(self.density_zones)} зон.", "INFO")
                
            return self.density_zones
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка расчета зон плотности: {e}")
            self.density_zones = [] # Clear zones in case of error
            return []
    
    @profile_me(filename_prefix="dm_on_websocket_message")
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
                if self.on_log: self.on_log(f"Данные стакана заявок для {self.symbol} обновлены через WebSocket.", "DEBUG")
                
        except json.JSONDecodeError as json_err:
            if self.on_error: self.on_error(f"Ошибка декодирования JSON из WebSocket для {self.symbol}: {json_err} - Сообщение: {message[:100]}...", "ERROR")
        except Exception as e: # Catch other potential errors
            if self.on_error:
                self.on_error(f"Непредвиденная ошибка обработки WebSocket сообщения для {self.symbol}: {e}")
    
    def on_websocket_error(self, ws, error):
        """Обработка ошибок WebSocket"""
        # Проверяем, относится ли ошибка к текущему активному соединению
        if self.ws == ws: # Check if the error is from the current WebSocket instance
            if self.on_error:
                self.on_error(f"WebSocket ошибка для {self.symbol}: {error}", "ERROR")
        # else: # Error from an old/stale WebSocket instance, can be ignored or logged as debug
            # if self.on_log: self.on_log(f"Получена ошибка от старого/неактивного WebSocket соединения: {error}", "DEBUG")

    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработка закрытия WebSocket"""
        is_current_ws_instance = (self.ws == ws) # Check if the close event is for the current ws

        if is_current_ws_instance:
            # If self.ws is None, it means stop_websocket was called, so it's an expected closure.
            is_expected_manual_close = (self.ws is None) 
            
            if is_expected_manual_close:
                if self.on_log: self.on_log(f"WebSocket соединение для {self.symbol} закрыто пользователем (stop_websocket).", "INFO")
            elif close_status_code == 1000 or close_status_code == 1001:
                if self.on_log: self.on_log(f"WebSocket соединение для {self.symbol} закрыто штатно (код: {close_status_code}, причина: {close_msg}).", "INFO")
            else: # Unexpected close for the current WebSocket instance
                if self.on_log:
                    self.on_log(f"WebSocket соединение для {self.symbol} неожиданно закрыто (код: {close_status_code}, причина: {close_msg}). Попытка переподключения через 5 секунд.", "WARNING")
                
                # Cancel any existing reconnection timer before starting a new one
                if hasattr(self, 'ws_recon_timer') and self.ws_recon_timer is not None and self.ws_recon_timer.is_alive():
                    self.ws_recon_timer.cancel()
                
                self.ws_recon_timer = threading.Timer(5.0, self.start_websocket)
                self.ws_recon_timer.daemon = True 
                self.ws_recon_timer.start()
        else: # Close event from an old WebSocket instance
             if self.on_log: self.on_log(f"Получено событие закрытия от старого/неактивного WebSocket соединения для {self.symbol} (код: {close_status_code}).", "DEBUG")


    def _on_websocket_open(self, ws):
        """Колбэк при открытии WebSocket соединения."""
        if self.on_log:
            self.on_log(f"WebSocket соединение для {self.symbol} успешно открыто.", "SUCCESS")

    def start_websocket(self):
        """Запуск WebSocket для стакана заявок"""
        try:
            # Cancel any pending reconnection timer if start is called explicitly
            if hasattr(self, 'ws_recon_timer') and self.ws_recon_timer is not None and self.ws_recon_timer.is_alive():
                self.ws_recon_timer.cancel()
                if self.on_log: self.on_log("Таймер переподключения WebSocket отменен из-за ручного запуска.", "DEBUG")

            if self.ws and hasattr(self.ws, 'sock') and self.ws.sock and self.ws.sock.connected:
                if self.on_log: self.on_log(f"WebSocket для {self.symbol} уже подключен или в процессе подключения. Для перезапуска используйте restart_websocket.", "DEBUG")
                return

            if self.on_log: self.on_log(f"Попытка запуска WebSocket для {self.symbol}...", "INFO")
            
            symbol_lower = self.symbol.lower()
            ws_url = f"wss://stream.binance.com:9443/ws/{symbol_lower}@depth20@100ms"
            
            current_ws = websocket.WebSocketApp(ws_url,
                                           on_message=self.on_websocket_message,
                                           on_error=self.on_websocket_error,
                                           on_close=self.on_websocket_close,
                                           on_open=self._on_websocket_open) # Added on_open callback
            self.ws = current_ws 
            
            ws_thread = threading.Thread(target=lambda: current_ws.run_forever(ping_interval=30, ping_timeout=10), daemon=True)
            ws_thread.name = f"WebSocketThread-{self.symbol}" # Naming thread for easier debugging
            ws_thread.start()
            
            if self.on_log:
                self.on_log(f"Поток WebSocket для {self.symbol} запущен.", "DEBUG")
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Критическая ошибка при запуске WebSocket для {self.symbol}: {e}", "ERROR")
    
    def restart_websocket(self):
        """Перезапуск WebSocket соединения"""
        if self.on_log: self.on_log(f"Перезапуск WebSocket для {self.symbol} инициирован...", "INFO")
        
        current_ws_instance = self.ws # Store current ws instance
        self.ws = None # Signal that this is an intentional stop for on_websocket_close
        
        if current_ws_instance and hasattr(current_ws_instance, 'keep_running') and current_ws_instance.keep_running:
            if self.on_log: self.on_log("Остановка существующего WebSocket соединения перед перезапуском...", "DEBUG")
            try:
                current_ws_instance.close()
            except Exception as e:
                if self.on_error: self.on_error(f"Ошибка при закрытии старого WebSocket сокета при перезапуске: {e}", "WARNING")
        
        # Запуск нового соединения будет инициирован через on_close или напрямую, если ws уже был None
        # Для большей предсказуемости, вызываем start_websocket напрямую.
        # on_close для старого сокета теперь не должен вызывать start_websocket из-за self.ws = None
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