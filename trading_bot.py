import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
import numpy as np
import requests
import json
import threading
import time
from datetime import datetime, timedelta
import logging
import warnings
warnings.filterwarnings('ignore')

# Попытка импорта дополнительных библиотек
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ websocket-client не установлен. Стакан заявок будет недоступен.")
    print("Установите: pip install websocket-client")

try:
    from sklearn.cluster import DBSCAN
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn не установлен. ML функции будут недоступны.")
    print("Установите: pip install scikit-learn")

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🚀 Advanced Trading Bot - Зоны плотности")
        self.root.geometry("1400x900")
        self.root.configure(bg='#1e1e1e')
        
        # Стиль интерфейса
        self.setup_styles()
        
        # Торговые параметры
        self.symbol = 'BTCUSDT'
        self.interval = '1h'
        self.balance = 10000  # Демо баланс
        self.position_size = 0
        self.entry_price = 0
        self.position_type = None
        
        # Данные
        self.df = None
        self.density_zones = []
        self.orderbook_data = {'bids': [], 'asks': []}
        self.ws = None
        self.ml_model = None
        if SKLEARN_AVAILABLE:
            self.scaler = StandardScaler()
        else:
            self.scaler = None
        
        # Создание интерфейса
        self.create_interface()
        if SKLEARN_AVAILABLE:
            self.setup_ml_model()
        
        # Запуск обновления данных
        self.update_data()
        if WEBSOCKET_AVAILABLE:
            self.start_websocket()
        
    def setup_styles(self):
        """Настройка стилей интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Кастомные стили
        style.configure('Title.TLabel', 
                       background='#1e1e1e', 
                       foreground='#00ff88', 
                       font=('Arial', 16, 'bold'))
        
        style.configure('Info.TLabel', 
                       background='#2d2d2d', 
                       foreground='#ffffff', 
                       font=('Arial', 10))
        
        style.configure('Success.TLabel', 
                       background='#2d2d2d', 
                       foreground='#00ff88', 
                       font=('Arial', 10, 'bold'))
        
        style.configure('Error.TLabel', 
                       background='#2d2d2d', 
                       foreground='#ff4444', 
                       font=('Arial', 10, 'bold'))
    
    def create_interface(self):
        """Создание главного интерфейса"""
        # Главная рамка
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="🎯 ТОРГОВЫЙ БОТ - ЗОНЫ ПЛОТНОСТИ", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Верхняя панель управления
        self.create_control_panel(main_frame)
        
        # Основная область с графиками
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # График цены (левая часть)
        self.create_price_chart(content_frame)
        
        # Правая панель
        right_panel = ttk.Frame(content_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        # Стакан заявок
        self.create_orderbook_widget(right_panel)
        
        # Информационная панель
        self.create_info_panel(right_panel)
        
        # Панель логов
        self.create_log_panel(right_panel)
    
    def create_control_panel(self, parent):
        """Панель управления"""
        control_frame = ttk.LabelFrame(parent, text="⚙️ Настройки торговли", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Первая строка
        row1 = ttk.Frame(control_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row1, text="📊 Пара:").pack(side=tk.LEFT)
        self.symbol_var = tk.StringVar(value='BTCUSDT')
        symbol_combo = ttk.Combobox(row1, textvariable=self.symbol_var, 
                                   values=['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'BNBUSDT', 'XRPUSDT'],
                                   width=12)
        symbol_combo.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(row1, text="⏰ Таймфрейм:").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value='1h')
        interval_combo = ttk.Combobox(row1, textvariable=self.interval_var,
                                     values=['1m', '5m', '15m', '1h', '4h', '1d'],
                                     width=8)
        interval_combo.pack(side=tk.LEFT, padx=(5, 20))
        
        # Кнопки управления
        ttk.Button(row1, text="🔄 Обновить", command=self.update_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="🎯 Авто-торговля", command=self.toggle_trading).pack(side=tk.LEFT, padx=5)
        
        # Статус
        self.status_label = ttk.Label(row1, text="📡 Подключено", style='Success.TLabel')
        self.status_label.pack(side=tk.RIGHT)
    
    def create_price_chart(self, parent):
        """График цены с зонами плотности"""
        chart_frame = ttk.LabelFrame(parent, text="📈 График цены и зоны плотности", padding=5)
        chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.fig, self.ax = plt.subplots(figsize=(12, 8), facecolor='#1e1e1e')
        self.ax.set_facecolor('#2d2d2d')
        self.ax.tick_params(colors='white')
        self.ax.set_xlabel('Время', color='white')
        self.ax.set_ylabel('Цена', color='white')
        
        self.canvas = FigureCanvasTkAgg(self.fig, chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def create_orderbook_widget(self, parent):
        """Виджет стакана заявок"""
        orderbook_frame = ttk.LabelFrame(parent, text="📋 Стакан заявок", padding=5)
        orderbook_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Заголовки
        headers_frame = ttk.Frame(orderbook_frame)
        headers_frame.pack(fill=tk.X)
        
        ttk.Label(headers_frame, text="Цена", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers_frame, text="Объем", font=('Arial', 9, 'bold')).pack(side=tk.RIGHT, padx=5)
        
        # Скроллируемая область
        canvas_frame = ttk.Frame(orderbook_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        orderbook_canvas = tk.Canvas(canvas_frame, bg='#2d2d2d', height=200)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=orderbook_canvas.yview)
        
        self.orderbook_frame = ttk.Frame(orderbook_canvas)
        orderbook_canvas.create_window((0, 0), window=self.orderbook_frame, anchor="nw")
        orderbook_canvas.configure(yscrollcommand=scrollbar.set)
        
        orderbook_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_info_panel(self, parent):
        """Информационная панель"""
        info_frame = ttk.LabelFrame(parent, text="💼 Торговая информация", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Баланс
        self.balance_label = ttk.Label(info_frame, text=f"💰 Баланс: ${self.balance:,.2f}", style='Info.TLabel')
        self.balance_label.pack(anchor=tk.W)
        
        # Позиция
        self.position_label = ttk.Label(info_frame, text="📊 Позиция: Нет", style='Info.TLabel')
        self.position_label.pack(anchor=tk.W)
        
        # P&L
        self.pnl_label = ttk.Label(info_frame, text="📈 P&L: $0.00", style='Info.TLabel')
        self.pnl_label.pack(anchor=tk.W)
        
        # ML сигнал
        self.ml_signal_label = ttk.Label(info_frame, text="🤖 ML Сигнал: Анализ...", style='Info.TLabel')
        self.ml_signal_label.pack(anchor=tk.W)
    
    def create_log_panel(self, parent):
        """Панель логов"""
        log_frame = ttk.LabelFrame(parent, text="📝 Лог операций", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=10, bg='#2d2d2d', fg='white', 
                               font=('Consolas', 9))
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")
    
    def log_message(self, message, level="INFO"):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}\n"
        
        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)
        
        # Цветовая индикация
        if level == "ERROR":
            self.log_text.tag_add("error", f"end-{len(formatted_message)}c", "end-1c")
            self.log_text.tag_config("error", foreground="#ff4444")
        elif level == "SUCCESS":
            self.log_text.tag_add("success", f"end-{len(formatted_message)}c", "end-1c")
            self.log_text.tag_config("success", foreground="#00ff88")
        
        logger.info(message)
    
    def get_kline_data(self, symbol='BTCUSDT', interval='1h', limit=500):
        """Получение данных свечей"""
        try:
            url = 'https://api.binance.com/api/v3/klines'
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Конвертация типов
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            self.log_message(f"Ошибка получения данных: {e}", "ERROR")
            return None
    
    def calculate_density_zones(self, df, volume_threshold=0.7):
        """Расчет зон плотности на основе объема"""
        if df is None or len(df) < 20:
            return []
        
        try:
            # Фильтрация высокообъемных свечей
            volume_quantile = df['volume'].quantile(volume_threshold)
            high_volume_data = df[df['volume'] >= volume_quantile]
            
            if len(high_volume_data) < 5:
                return []
            
            # Создание ценовых уровней для кластеризации
            price_levels = []
            volumes = []
            
            for idx, row in high_volume_data.iterrows():
                # Добавляем максимумы и минимумы с их объемами
                price_levels.extend([row['high'], row['low'], row['close']])
                volumes.extend([row['volume']] * 3)
            
            if len(price_levels) < 10:
                return []
            
            # Простая кластеризация без sklearn
            zones = []
            if SKLEARN_AVAILABLE:
                # Кластеризация ценовых уровней с DBSCAN
                price_array = np.array(price_levels).reshape(-1, 1)
                
                # Адаптивный расчет eps на основе волатильности
                price_range = df['high'].max() - df['low'].min()
                eps = price_range * 0.01  # 1% от диапазона цен
                
                clustering = DBSCAN(eps=eps, min_samples=3).fit(price_array)
                labels = clustering.labels_
                
                # Создание зон плотности
                unique_labels = set(labels)
                
                for label in unique_labels:
                    if label == -1:  # Игнорируем шум
                        continue
                    
                    cluster_mask = labels == label
                    cluster_prices = np.array(price_levels)[cluster_mask]
                    cluster_volumes = np.array(volumes)[cluster_mask]
                    
                    if len(cluster_prices) < 3:
                        continue
                    
                    zone_center = np.mean(cluster_prices)
                    zone_strength = np.sum(cluster_volumes)
                    zone_width = np.std(cluster_prices) * 2
                    
                    # Определение типа зоны (поддержка/сопротивление)
                    current_price = df['close'].iloc[-1]
                    zone_type = 'support' if zone_center < current_price else 'resistance'
                    
                    # Подсчет касаний зоны
                    touches = 0
                    for _, row in df.iterrows():
                        if (zone_center - zone_width <= row['low'] <= zone_center + zone_width or
                            zone_center - zone_width <= row['high'] <= zone_center + zone_width):
                            touches += 1
                    
                    zones.append({
                        'center': zone_center,
                        'strength': zone_strength,
                        'width': zone_width,
                        'type': zone_type,
                        'touches': touches,
                        'alpha': min(0.8, touches / 10 + 0.2)  # Прозрачность от касаний
                    })
            else:
                # Упрощенный алгоритм без sklearn
                price_levels_sorted = sorted(set(price_levels))
                current_price = df['close'].iloc[-1]
                
                # Поиск уровней поддержки и сопротивления
                for i in range(0, len(price_levels_sorted) - 2, 5):  # Каждый 5-й уровень
                    level = price_levels_sorted[i]
                    
                    # Подсчет касаний
                    touches = sum(1 for p in price_levels if abs(p - level) < level * 0.01)
                    
                    if touches >= 3:  # Минимум 3 касания
                        zone_type = 'support' if level < current_price else 'resistance'
                        
                        zones.append({
                            'center': level,
                            'strength': touches * 1000,  # Условная сила
                            'width': level * 0.005,  # 0.5% от цены
                            'type': zone_type,
                            'touches': touches,
                            'alpha': min(0.8, touches / 10 + 0.3)
                        })
            
            # Сортировка по силе
            zones.sort(key=lambda x: x['strength'], reverse=True)
            return zones[:10]  # Топ-10 зон
            
        except Exception as e:
            self.log_message(f"Ошибка расчета зон плотности: {e}", "ERROR")
            return []
    
    def setup_ml_model(self):
        """Настройка ML модели для предсказания направления цены"""
        if not SKLEARN_AVAILABLE:
            return
            
        try:
            # Создаем простую модель Random Forest
            self.ml_model = RandomForestClassifier(n_estimators=50, random_state=42)
            self.log_message("ML модель инициализирована", "SUCCESS")
        except Exception as e:
            self.log_message(f"Ошибка инициализации ML модели: {e}", "ERROR")
    
    def prepare_ml_features(self, df):
        """Подготовка признаков для ML модели"""
        if df is None or len(df) < 20 or not SKLEARN_AVAILABLE:
            return None, None
        
        try:
            # Технические индикаторы
            df['sma_10'] = df['close'].rolling(10).mean()
            df['sma_20'] = df['close'].rolling(20).mean()
            df['rsi'] = self.calculate_rsi(df['close'])
            df['volume_sma'] = df['volume'].rolling(10).mean()
            
            # Признаки
            features = []
            targets = []
            
            for i in range(20, len(df) - 1):
                feature_vector = [
                    (df['close'].iloc[i] - df['sma_10'].iloc[i]) / df['sma_10'].iloc[i],
                    (df['close'].iloc[i] - df['sma_20'].iloc[i]) / df['sma_20'].iloc[i],
                    df['rsi'].iloc[i] / 100,
                    (df['volume'].iloc[i] - df['volume_sma'].iloc[i]) / df['volume_sma'].iloc[i],
                    (df['high'].iloc[i] - df['low'].iloc[i]) / df['close'].iloc[i]
                ]
                
                # Целевая переменная (направление следующей свечи)
                target = 1 if df['close'].iloc[i + 1] > df['close'].iloc[i] else 0
                
                if not any(pd.isna(feature_vector)):
                    features.append(feature_vector)
                    targets.append(target)
            
            return np.array(features), np.array(targets)
            
        except Exception as e:
            self.log_message(f"Ошибка подготовки ML признаков: {e}", "ERROR")
            return None, None
    
    def calculate_rsi(self, prices, period=14):
        """Расчет RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def train_ml_model(self, df):
        """Обучение ML модели"""
        if self.ml_model is None or not SKLEARN_AVAILABLE:
            return
        
        try:
            features, targets = self.prepare_ml_features(df)
            if features is not None and len(features) > 50:
                # Нормализация признаков
                features_scaled = self.scaler.fit_transform(features)
                
                # Обучение модели
                self.ml_model.fit(features_scaled, targets)
                
                # Оценка точности
                score = self.ml_model.score(features_scaled, targets)
                self.log_message(f"ML модель обучена. Точность: {score:.2%}", "SUCCESS")
                
        except Exception as e:
            self.log_message(f"Ошибка обучения ML модели: {e}", "ERROR")
    
    def get_ml_prediction(self, df):
        """Получение ML предсказания"""
        if self.ml_model is None or df is None or len(df) < 20 or not SKLEARN_AVAILABLE:
            return "ML недоступен"
        
        try:
            # Подготовка последних признаков
            df_temp = df.copy()
            df_temp['sma_10'] = df_temp['close'].rolling(10).mean()
            df_temp['sma_20'] = df_temp['close'].rolling(20).mean()
            df_temp['rsi'] = self.calculate_rsi(df_temp['close'])
            df_temp['volume_sma'] = df_temp['volume'].rolling(10).mean()
            
            last_row = df_temp.iloc[-1]
            feature_vector = [
                (last_row['close'] - last_row['sma_10']) / last_row['sma_10'],
                (last_row['close'] - last_row['sma_20']) / last_row['sma_20'],
                last_row['rsi'] / 100,
                (last_row['volume'] - last_row['volume_sma']) / last_row['volume_sma'],
                (last_row['high'] - last_row['low']) / last_row['close']
            ]
            
            if any(pd.isna(feature_vector)):
                return "Анализ..."
            
            # Нормализация и предсказание
            feature_scaled = self.scaler.transform([feature_vector])
            prediction = self.ml_model.predict(feature_scaled)[0]
            probability = self.ml_model.predict_proba(feature_scaled)[0]
            
            confidence = max(probability)
            direction = "📈 ПОКУПКА" if prediction == 1 else "📉 ПРОДАЖА"
            
            return f"{direction} ({confidence:.1%})"
            
        except Exception as e:
            return "Ошибка анализа"
    
    def update_chart(self):
        """Обновление графика"""
        if self.df is None:
            return
        
        try:
            self.ax.clear()
            
            # График цены
            self.ax.plot(self.df.index, self.df['close'], 'white', linewidth=1.5, label='Цена')
            
            # Зоны плотности
            current_price = self.df['close'].iloc[-1]
            
            for zone in self.density_zones:
                color = '#00ff88' if zone['type'] == 'support' else '#ff4444'
                
                # Зона как прямоугольник
                y_min = zone['center'] - zone['width']
                y_max = zone['center'] + zone['width']
                
                self.ax.axhspan(y_min, y_max, alpha=zone['alpha'], 
                               color=color, label=f"{zone['type'].title()} Zone")
                
                # Центральная линия зоны
                self.ax.axhline(y=zone['center'], color=color, 
                               linestyle='--', alpha=0.8, linewidth=1)
                
                # Подпись зоны
                zone_label = f"{zone['type'][:3].upper()}: ${zone['center']:.2f}"
                self.ax.text(self.df.index[-20], zone['center'], zone_label,
                           color=color, fontsize=8, fontweight='bold')
            
            # Текущая позиция
            if self.position_size != 0:
                self.ax.axhline(y=self.entry_price, color='yellow', 
                               linestyle='-', linewidth=2, alpha=0.8, label='Вход')
            
            # Настройка графика
            self.ax.set_facecolor('#2d2d2d')
            self.ax.tick_params(colors='white')
            self.ax.set_xlabel('Время', color='white')
            self.ax.set_ylabel('Цена USDT', color='white')
            self.ax.set_title(f'{self.symbol} - {self.interval} | Зоны плотности', 
                            color='white', fontweight='bold')
            
            # Сетка
            self.ax.grid(True, alpha=0.3)
            
            # Легенда
            if self.density_zones:
                self.ax.legend(loc='upper left', facecolor='#2d2d2d', 
                             edgecolor='white', labelcolor='white')
            
            self.canvas.draw()
            
        except Exception as e:
            self.log_message(f"Ошибка обновления графика: {e}", "ERROR")
    
    def update_orderbook_display(self):
        """Обновление отображения стакана заявок"""
        try:
            # Очистка предыдущих данных
            for widget in self.orderbook_frame.winfo_children():
                widget.destroy()
            
            bids = self.orderbook_data.get('bids', [])[:10]
            asks = self.orderbook_data.get('asks', [])[:10]
            
            # Продажи (asks) - красные
            for i, (price, volume) in enumerate(asks[::-1]):  # Обратный порядок
                row_frame = ttk.Frame(self.orderbook_frame)
                row_frame.pack(fill=tk.X, pady=1)
                
                price_label = tk.Label(row_frame, text=f"{float(price):.2f}", 
                                     fg='#ff4444', bg='#2d2d2d', font=('Arial', 9))
                price_label.pack(side=tk.LEFT, padx=5)
                
                volume_label = tk.Label(row_frame, text=f"{float(volume):.4f}", 
                                      fg='white', bg='#2d2d2d', font=('Arial', 9))
                volume_label.pack(side=tk.RIGHT, padx=5)
            
            # Разделитель
            separator = tk.Frame(self.orderbook_frame, height=2, bg='#555555')
            separator.pack(fill=tk.X, pady=2)
            
            # Покупки (bids) - зеленые
            for i, (price, volume) in enumerate(bids):
                row_frame = ttk.Frame(self.orderbook_frame)
                row_frame.pack(fill=tk.X, pady=1)
                
                price_label = tk.Label(row_frame, text=f"{float(price):.2f}", 
                                     fg='#00ff88', bg='#2d2d2d', font=('Arial', 9))
                price_label.pack(side=tk.LEFT, padx=5)
                
                volume_label = tk.Label(row_frame, text=f"{float(volume):.4f}", 
                                      fg='white', bg='#2d2d2d', font=('Arial', 9))
                volume_label.pack(side=tk.RIGHT, padx=5)
                
        except Exception as e:
            self.log_message(f"Ошибка обновления стакана: {e}", "ERROR")
    
    def on_websocket_message(self, ws, message):
        """Обработка сообщений WebSocket"""
        try:
            data = json.loads(message)
            
            if 'bids' in data and 'asks' in data:
                self.orderbook_data = {
                    'bids': data['bids'][:20],
                    'asks': data['asks'][:20]
                }
                
                # Обновление интерфейса в главном потоке
                self.root.after(0, self.update_orderbook_display)
                
        except Exception as e:
            self.log_message(f"Ошибка обработки WebSocket: {e}", "ERROR")
    
    def on_websocket_error(self, ws, error):
        """Обработка ошибок WebSocket"""
        self.log_message(f"WebSocket ошибка: {error}", "ERROR")
    
    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработка закрытия WebSocket"""
        self.log_message("WebSocket соединение закрыто", "ERROR")
        # Переподключение через 5 секунд
        threading.Timer(5.0, self.start_websocket).start()
    
    def start_websocket(self):
        """Запуск WebSocket для стакана заявок"""
        if not WEBSOCKET_AVAILABLE:
            self.log_message("WebSocket недоступен - модуль не установлен", "ERROR")
            return
            
        try:
            if self.ws:
                self.ws.close()
            
            symbol = self.symbol_var.get().lower()
            ws_url = f"wss://stream.binance.com:9443/ws/{symbol}@depth20@100ms"
            
            self.ws = websocket.WebSocketApp(ws_url,
                                           on_message=self.on_websocket_message,
                                           on_error=self.on_websocket_error,
                                           on_close=self.on_websocket_close)
            
            # Запуск в отдельном потоке
            ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            ws_thread.start()
            
            self.log_message("WebSocket подключен", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"Ошибка запуска WebSocket: {e}", "ERROR")
    
    def check_trading_signals(self):
        """Проверка торговых сигналов"""
        if not self.density_zones or self.df is None:
            return
        
        try:
            current_price = self.df['close'].iloc[-1]
            
            # Проверка сигналов для каждой зоны
            for zone in self.density_zones:
                distance = abs(current_price - zone['center'])
                zone_threshold = zone['center'] * 0.01  # 1% от цены
                
                if distance <= zone_threshold:
                    if zone['type'] == 'support' and self.position_size == 0:
                        # Сигнал на покупку
                        self.execute_buy_order(current_price, zone)
                    elif zone['type'] == 'resistance' and self.position_size > 0:
                        # Сигнал на продажу
                        self.execute_sell_order(current_price, zone)
                        
        except Exception as e:
            self.log_message(f"Ошибка проверки сигналов: {e}", "ERROR")
    
    def execute_buy_order(self, price, zone):
        """Выполнение покупки"""
        try:
            if self.position_size != 0:
                return  # Уже есть позиция
            
            # Расчет размера позиции (10% от баланса)
            position_value = self.balance * 0.1
            quantity = position_value / price
            
            # Имитация исполнения ордера
            self.position_size = quantity
            self.entry_price = price
            self.position_type = 'LONG'
            self.balance -= position_value
            
            self.log_message(f"🟢 ПОКУПКА: {quantity:.6f} по цене ${price:.2f} | Зона: ${zone['center']:.2f}", "SUCCESS")
            self.update_position_info()
            
        except Exception as e:
            self.log_message(f"Ошибка покупки: {e}", "ERROR")
    
    def execute_sell_order(self, price, zone):
        """Выполнение продажи"""
        try:
            if self.position_size == 0:
                return  # Нет позиции
            
            # Расчет прибыли/убытка
            position_value = self.position_size * price
            pnl = position_value - (self.position_size * self.entry_price)
            
            # Имитация исполнения ордера
            self.balance += position_value
            
            self.log_message(f"🔴 ПРОДАЖА: {self.position_size:.6f} по цене ${price:.2f} | P&L: ${pnl:.2f}", "SUCCESS" if pnl > 0 else "ERROR")
            
            # Сброс позиции
            self.position_size = 0
            self.entry_price = 0
            self.position_type = None
            
            self.update_position_info()
            
        except Exception as e:
            self.log_message(f"Ошибка продажи: {e}", "ERROR")
    
    def update_position_info(self):
        """Обновление информации о позиции"""
        try:
            # Баланс
            self.balance_label.config(text=f"💰 Баланс: ${self.balance:,.2f}")
            
            # Позиция
            if self.position_size > 0:
                self.position_label.config(text=f"📊 Позиция: {self.position_type} {self.position_size:.6f}")
                
                # P&L
                if self.df is not None:
                    current_price = self.df['close'].iloc[-1]
                    current_value = self.position_size * current_price
                    entry_value = self.position_size * self.entry_price
                    pnl = current_value - entry_value
                    
                    pnl_text = f"📈 P&L: ${pnl:.2f} ({(pnl/entry_value)*100:.2f}%)"
                    if pnl > 0:
                        self.pnl_label.config(text=pnl_text, style='Success.TLabel')
                    else:
                        self.pnl_label.config(text=pnl_text, style='Error.TLabel')
            else:
                self.position_label.config(text="📊 Позиция: Нет")
                self.pnl_label.config(text="📈 P&L: $0.00", style='Info.TLabel')
            
            # ML сигнал
            if self.df is not None:
                ml_signal = self.get_ml_prediction(self.df)
                self.ml_signal_label.config(text=f"🤖 ML Сигнал: {ml_signal}")
                
        except Exception as e:
            self.log_message(f"Ошибка обновления информации: {e}", "ERROR")
    
    def update_data(self):
        """Обновление данных"""
        try:
            self.symbol = self.symbol_var.get()
            self.interval = self.interval_var.get()
            
            self.log_message(f"Обновление данных для {self.symbol} ({self.interval})...")
            
            # Получение новых данных
            new_df = self.get_kline_data(self.symbol, self.interval)
            
            if new_df is not None:
                self.df = new_df
                
                # Расчет зон плотности
                self.density_zones = self.calculate_density_zones(self.df)
                self.log_message(f"Найдено {len(self.density_zones)} зон плотности")
                
                # Обучение ML модели
                if SKLEARN_AVAILABLE:
                    self.train_ml_model(self.df)
                
                # Обновление графика
                self.update_chart()
                
                # Обновление информации
                self.update_position_info()
                
                # Проверка торговых сигналов
                self.check_trading_signals()
                
                # Перезапуск WebSocket для новой пары
                if WEBSOCKET_AVAILABLE:
                    self.start_websocket()
                
                self.status_label.config(text="📡 Обновлено", style='Success.TLabel')
                
            else:
                self.status_label.config(text="❌ Ошибка данных", style='Error.TLabel')
                
        except Exception as e:
            self.log_message(f"Ошибка обновления данных: {e}", "ERROR")
            self.status_label.config(text="❌ Ошибка", style='Error.TLabel')
    
    def toggle_trading(self):
        """Переключение автоматической торговли"""
        if hasattr(self, 'auto_trading') and self.auto_trading:
            self.auto_trading = False
            self.log_message("Автоматическая торговля ОСТАНОВЛЕНА", "ERROR")
        else:
            self.auto_trading = True
            self.log_message("Автоматическая торговля ЗАПУЩЕНА", "SUCCESS")
            self.auto_trading_loop()
    
    def auto_trading_loop(self):
        """Цикл автоматической торговли"""
        if hasattr(self, 'auto_trading') and self.auto_trading:
            try:
                # Обновление данных
                new_df = self.get_kline_data(self.symbol, self.interval, 100)
                if new_df is not None:
                    self.df = new_df
                    
                    # Пересчет зон
                    self.density_zones = self.calculate_density_zones(self.df)
                    
                    # Проверка сигналов
                    self.check_trading_signals()
                    
                    # Обновление интерфейса
                    self.update_chart()
                    self.update_position_info()
                
                # Следующая итерация через 30 секунд
                self.root.after(30000, self.auto_trading_loop)
                
            except Exception as e:
                self.log_message(f"Ошибка в авто-торговле: {e}", "ERROR")
                self.auto_trading = False
    
    def run(self):
        """Запуск приложения"""
        try:
            self.log_message("🚀 Торговый бот запущен!", "SUCCESS")
            self.log_message("📊 Инициализация интерфейса...")
            self.log_message("🔗 Подключение к Binance API...")
            
            # Горячие клавиши
            self.root.bind('<F5>', lambda e: self.update_data())
            self.root.bind('<F1>', lambda e: self.show_help())
            
            self.root.mainloop()
            
        except KeyboardInterrupt:
            self.log_message("Получен сигнал прерывания", "ERROR")
        except Exception as e:
            self.log_message(f"Критическая ошибка: {e}", "ERROR")
        finally:
            if self.ws:
                self.ws.close()
            self.log_message("Торговый бот остановлен", "ERROR")
    
    def show_help(self):
        """Показ справки"""
        help_text = """
🎯 ТОРГОВЫЙ БОТ - СПРАВКА

📊 Основные функции:
• Анализ зон плотности на основе объема
• Автоматические торговые сигналы
• ML предсказания направления цены
• Стакан заявок в реальном времени

⌨️ Горячие клавиши:
• F5 - Обновить данные
• F1 - Показать справку

🎨 Цветовая схема:
• Зеленые зоны - Поддержка
• Красные зоны - Сопротивление
• Желтая линия - Цена входа

⚠️ Внимание:
Это демо-версия для обучения!
Используйте на свой страх и риск.
        """
        
        messagebox.showinfo("Справка", help_text)


# Точка входа
if __name__ == "__main__":
    try:
        # Создание и запуск бота
        bot = TradingBot()
        bot.run()
        
    except Exception as e:
        print(f"Ошибка запуска: {e}")
        input("Нажмите Enter для выхода...")
