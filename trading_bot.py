import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import logging
import warnings
import os
import time
import requests
import threading
from datetime import datetime, timedelta

# Импорт модульных компонентов
from data_manager import DataManager
from chart_manager import ChartManager
from ml_manager import MLManager
from trading_manager import TradingManager
from settings_manager import SettingsManager

# Попытка импорта matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️ matplotlib не установлен. Графики будут недоступны.")
    print("Установите: pip install matplotlib")

# Попытка импорта pandas и numpy
try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("⚠️ pandas/numpy не установлены. Некоторые функции будут недоступны.")
    print("Установите: pip install pandas numpy")
    # Создаем заглушки для базовой функциональности
    class MockDataFrame:
        def __init__(self, data=None, columns=None, **kwargs):
            self.data = data or []
            self.columns = columns or []
        def empty(self): return len(self.data) == 0
        def __len__(self): return len(self.data)
        def __getitem__(self, key): return self.data
        def iloc(self): return self
        def dropna(self): return self
        def copy(self): return self
    pd = type('MockPandas', (), {'DataFrame': MockDataFrame})()
    np = type('MockNumpy', (), {'array': list, 'mean': lambda x: sum(x)/len(x) if x else 0})()

warnings.filterwarnings('ignore')

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ websocket-client не установлен. Стакан заявок будет недоступен.")
    print("Установите: pip install websocket-client")

try:
    from sklearn.cluster import DBSCAN
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler, RobustScaler
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.neural_network import MLPClassifier
    from sklearn.svm import SVC
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn не установлен. ML функции будут недоступны.")
    print("Установите: pip install scikit-learn")

class TradingBot:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🚀 Advanced Trading Bot v2.0 - AI Enhanced")
        self.root.geometry("1600x1000")
        self.root.configure(bg='#1e1e1e')
        
        # Стиль интерфейса
        self.setup_styles()
        
        # Инициализация модульных компонентов
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings
        
        # Создание основных фреймов интерфейса
        self.create_main_frames()
        
        # Инициализация модулей с передачей необходимых параметров
        self.data_manager = DataManager(
            symbol=self.settings['trading']['symbol'],
            interval=self.settings['trading']['interval']
        )
        
        self.chart_manager = ChartManager(
            master=self.root,
            chart_frame=self.chart_frame
        )
        
        self.ml_manager = MLManager()
        
        self.trading_manager = TradingManager(
            symbol=self.settings['trading']['symbol'],
            mode=self.settings['trading']['mode']
        )
        
        # Настройка колбэков для обновления UI
        self.setup_callbacks()
        
        # Оптимизация производительности
        self.last_update_time = 0
        self.update_interval = 0.2  # Минимальный интервал между обновлениями (сек)
        self.is_updating = False
        self.chart_cache = {}
        self.ml_cache = {}
        
        # Инициализация ML-атрибутов
        self.current_model = 'RandomForest'
        
        # Инициализация ML-моделей и скейлера
        if SKLEARN_AVAILABLE:
            self.setup_ml_model()
        
        # Инициализация интерфейса
        self.create_ui_components()
        
        # Запуск получения данных
        self.start_data_stream()
    
    def create_main_frames(self):
        """Создание основных фреймов интерфейса"""
        # Основной контейнер
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Левая панель для графика
        self.chart_frame = ttk.Frame(self.main_container)
        self.chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Правая панель для контролов
        self.control_frame = ttk.Frame(self.main_container, width=300)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False, padx=(10, 0))
        self.control_frame.pack_propagate(False)
    
    def setup_callbacks(self):
        """Настройка колбэков между модулями"""
        # Колбэки для DataManager
        self.data_manager.on_data_updated = self.on_data_updated
        self.data_manager.on_orderbook_updated = self.on_orderbook_updated
        self.data_manager.on_error = self.log_message
        
        # Колбэки для ChartManager
        self.chart_manager.on_error = self.log_message
        
        # Колбэки для MLManager
        self.ml_manager.on_training_complete = self.on_ml_training_complete
        self.ml_manager.on_error = self.log_message
        
        # Колбэки для TradingManager
        self.trading_manager.on_position_update = self.on_position_update
        self.trading_manager.on_order_update = self.on_order_update
        self.trading_manager.on_error = self.log_message
        
        # Колбэки для SettingsManager
        self.settings_manager.on_settings_updated = self.on_settings_updated
        self.settings_manager.on_error = self.log_message
        self.settings_manager.on_log = self.log_message
    
    def start_data_stream(self):
        """Запуск потока данных"""
        # Получение исторических данных
        self.data_manager.get_kline_data()
        
        # Запуск WebSocket для стакана заявок
        self.data_manager.start_websocket()
        
        # Запуск периодического обновления данных
        self.schedule_data_update()
    
    def schedule_data_update(self):
        """Планирование регулярного обновления данных"""
        update_interval_ms = self.settings['general']['update_interval'] * 1000
        self.update_data()
        self.root.after(update_interval_ms, self.schedule_data_update)
    
    def update_data(self):
        """Обновление данных"""
        try:
            # Получение новых данных через DataManager
            self.data_manager.get_kline_data()
            
            # Расчет зон плотности
            if self.settings['chart']['show_density_zones']:
                self.data_manager.calculate_density_zones()
            
            # Обновление ML-модели при необходимости
            if self.settings['ml']['enabled'] and not self.ml_manager.is_training:
                df = self.data_manager.df
                if df is not None and len(df) > 50:
                    self.ml_manager.prepare_features(df)
            
            # Проверка торговых сигналов
            if self.settings['trading']['auto_trading']:
                self.check_trading_signals()
        except Exception as e:
            self.log_message(f"Ошибка обновления данных: {e}", "ERROR")
        self.ml_cache = {}
        
        # Флаги состояния
        self.auto_trading_enabled = False
    
    def create_ui_components(self):
        """Создание компонентов пользовательского интерфейса"""
        # Верхняя панель с основными контролами
        self.create_top_controls()
        
        # Панель с информацией о позиции
        self.create_position_panel()
        
        # Панель с настройками
        self.create_settings_panel()
        
        # Панель с логами
        self.create_log_panel()
        
        # Инициализация графика через ChartManager
        self.chart_manager.setup_chart()
        
        # Настройка обработчиков событий для графика
        self.chart_manager.setup_event_handlers()
        
        # Первоначальное обновление интерфейса
        self.update_ui_with_settings()
    
    def on_data_updated(self, df, density_zones):
        """Обработчик события обновления данных"""
        # Передача данных в ChartManager для отображения
        self.chart_manager.update_data(df, density_zones)
        
        # Обновление интерфейса
        self.update_ui_with_new_data()
    
    def on_orderbook_updated(self, orderbook_data):
        """Обработчик события обновления стакана заявок"""
        # Передача данных в ChartManager для отображения
        self.chart_manager.update_orderbook(orderbook_data)
    
    def on_ml_training_complete(self, accuracy):
        """Обработчик события завершения обучения ML-модели"""
        self.log_message(f"ML-модель обучена. Точность: {accuracy:.2%}", "SUCCESS")
        
        # Обновление интерфейса с новой информацией о модели
        if hasattr(self, 'ml_accuracy_label'):
            self.ml_accuracy_label.config(text=f"Точность: {accuracy:.2%}")
    
    def on_position_update(self, position):
        """Обработчик события обновления позиции"""
        # Обновление интерфейса с новой информацией о позиции
        self.update_position_display(position)
    
    def on_order_update(self, orders):
        """Обработчик события обновления ордеров"""
        # Обновление интерфейса с новой информацией об ордерах
        self.update_orders_display(orders)
    
    def on_settings_updated(self):
        """Обработчик события обновления настроек"""
        # Обновление настроек в модулях
        self.data_manager.set_symbol_interval(
            self.settings['trading']['symbol'],
            self.settings['trading']['interval']
        )
        
        # Обновление настроек графика
        self.chart_manager.update_settings(self.settings['chart'])
        
        # Обновление настроек торговли
        self.trading_manager.set_trading_params(
            leverage=self.settings['trading']['leverage'],
            risk_percent=self.settings['trading']['risk_percent'],
            take_profit_percent=self.settings['trading']['take_profit_percent'],
            stop_loss_percent=self.settings['trading']['stop_loss_percent'],
            trailing_stop=self.settings['trading']['trailing_stop'],
            trailing_percent=self.settings['trading']['trailing_percent']
        )
        
        # Обновление интерфейса
        self.update_ui_with_settings()
    
    def update_ui_with_new_data(self):
        """Обновление интерфейса при получении новых данных"""
        # Проверка на частые обновления
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return
        
        self.last_update_time = current_time
        
        # Обновление графика через ChartManager
        self.chart_manager.update_chart()
        
        # Обновление информации о цене
        if self.data_manager.df is not None and len(self.data_manager.df) > 0:
            last_price = self.data_manager.df.iloc[-1]['close']
            if hasattr(self, 'price_label'):
                self.price_label.config(text=f"Цена: {last_price:.2f}")
    
    def check_trading_signals(self):
        """Проверка торговых сигналов"""
        if not self.settings['trading']['auto_trading']:
            return
        
        try:
            df = self.data_manager.df
            if df is None or len(df) < 30:
                return
            
            # Получение предсказания от ML-модели
            if self.settings['ml']['enabled'] and self.ml_manager.model is not None:
                features = self.ml_manager.prepare_features(df)
                if features is not None:
                    prediction = self.ml_manager.predict(features)
                    
                    # Обработка сигнала через TradingManager
                    if prediction == 1:  # Сигнал на покупку
                        self.trading_manager.process_signal('buy', df.iloc[-1]['close'])
                    elif prediction == 0:  # Сигнал на продажу
                        self.trading_manager.process_signal('sell', df.iloc[-1]['close'])
        except Exception as e:
            self.log_message(f"Ошибка проверки сигналов: {e}", "ERROR")
        
        # Данные
        self.df = None
        self.density_zones = []
        self.orderbook_data = {'bids': [], 'asks': []}
        self.ws = None
        self.price_history = deque(maxlen=1000)  # История цен для анализа
        self.volume_history = deque(maxlen=1000)  # История объемов
        
        # ML модели
        self.ml_models = {}
        self.model_performance = {}
        self.current_model = 'RandomForest'
        if SKLEARN_AVAILABLE:
            self.scaler = RobustScaler()  # Более устойчивый к выбросам
        else:
            self.scaler = None
        
        # Настройки графика
        self.chart_settings = {
            'support_color': '#00ff88',
            'resistance_color': '#ff4444',
            'background_color': '#2d2d2d',
            'grid_alpha': 0.3,
            'zone_alpha': 0.4,
            'show_volume': True,
            'show_indicators': True,
            'chart_style': 'dark'
        }
        
        # Технические индикаторы
        self.indicators = {
            'sma_periods': [10, 20, 50],
            'ema_periods': [12, 26],
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'bb_period': 20,
            'bb_std': 2
        }
        
        # Создание интерфейса
        self.create_interface()
        if SKLEARN_AVAILABLE:
            self.setup_ml_model()  # ML модель
        
        # Загрузка сохраненных настроек
        self.load_settings()
        
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
        
        # Первая строка - основные настройки
        row1 = ttk.Frame(control_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row1, text="📊 Пара:").pack(side=tk.LEFT)
        self.symbol_var = tk.StringVar(value='BTCUSDT')
        symbol_combo = ttk.Combobox(row1, textvariable=self.symbol_var, 
                                   values=['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'BNBUSDT', 'XRPUSDT', 'SOLUSDT', 'DOTUSDT'],
                                   width=12)
        symbol_combo.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(row1, text="⏰ Таймфрейм:").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value='1h')
        interval_combo = ttk.Combobox(row1, textvariable=self.interval_var,
                                     values=['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'],
                                     width=8)
        interval_combo.pack(side=tk.LEFT, padx=(5, 20))
        
        # Кнопки управления
        ttk.Button(row1, text="🔄 Обновить", command=self.update_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="🎯 Авто-торговля", command=self.toggle_trading).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="🎨 Настройки графика", command=self.open_chart_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="🤖 ML Настройки", command=self.open_ml_settings).pack(side=tk.LEFT, padx=5)
        
        # Статус
        self.status_label = ttk.Label(row1, text="📡 Подключено", style='Success.TLabel')
        self.status_label.pack(side=tk.RIGHT)
        
        # Вторая строка - дополнительные настройки
        row2 = ttk.Frame(control_frame)
        row2.pack(fill=tk.X, pady=(5, 0))
        
        # ML модель
        ttk.Label(row2, text="🧠 ML Модель:").pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value='RandomForest')
        model_combo = ttk.Combobox(row2, textvariable=self.model_var,
                                  values=['RandomForest', 'GradientBoosting', 'NeuralNetwork', 'SVM'],
                                  width=15)
        model_combo.pack(side=tk.LEFT, padx=(5, 20))
        model_combo.bind('<<ComboboxSelected>>', self.on_model_change)
        
        # Показатели
        self.show_volume_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="📊 Объемы", variable=self.show_volume_var, 
                       command=self.update_chart).pack(side=tk.LEFT, padx=5)
        
        self.show_indicators_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="📈 Индикаторы", variable=self.show_indicators_var,
                       command=self.update_chart).pack(side=tk.LEFT, padx=5)
        
        # Точность модели
        self.accuracy_label = ttk.Label(row2, text="🎯 Точность: N/A", style='Info.TLabel')
        self.accuracy_label.pack(side=tk.RIGHT, padx=10)
    
    def create_price_chart(self, parent):
        """График цены с зонами плотности и расширенной функциональностью"""
        chart_frame = ttk.LabelFrame(parent, text="📈 Интерактивный график цены и анализ", padding=5)
        chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        if not MATPLOTLIB_AVAILABLE:
            # Показать сообщение о недоступности графиков
            no_chart_label = ttk.Label(chart_frame, 
                text="⚠️ Графики недоступны\n\nДля отображения графиков установите matplotlib:\npip install matplotlib",
                justify=tk.CENTER, font=('Arial', 12))
            no_chart_label.pack(expand=True)
            return
        
        # Создание фигуры с подграфиками
        self.fig, (self.ax_price, self.ax_volume, self.ax_indicators) = plt.subplots(
            3, 1, figsize=(14, 10), facecolor='#1e1e1e', 
            gridspec_kw={'height_ratios': [3, 1, 1], 'hspace': 0.1}
        )
        
        # Настройка основного графика цены
        self.ax_price.set_facecolor(self.chart_settings['background_color'])
        self.ax_price.tick_params(colors='white')
        self.ax_price.set_ylabel('Цена (USDT)', color='white', fontweight='bold')
        
        # Настройка графика объемов
        self.ax_volume.set_facecolor(self.chart_settings['background_color'])
        self.ax_volume.tick_params(colors='white')
        self.ax_volume.set_ylabel('Объем', color='white', fontweight='bold')
        
        # Настройка графика индикаторов
        self.ax_indicators.set_facecolor(self.chart_settings['background_color'])
        self.ax_indicators.tick_params(colors='white')
        self.ax_indicators.set_ylabel('RSI/MACD', color='white', fontweight='bold')
        self.ax_indicators.set_xlabel('Время', color='white', fontweight='bold')
        
        # Создание canvas
        self.canvas = FigureCanvasTkAgg(self.fig, chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Добавление панели навигации
        toolbar_frame = ttk.Frame(chart_frame)
        toolbar_frame.pack(fill=tk.X)
        
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()
        
        # Настройка интерактивности
        self.setup_chart_interactivity()
        
        # Инициализация селектора области
        self.rect_selector = None
    
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
    
    def setup_chart_interactivity(self):
        """Настройка интерактивности графика"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        # Подключение событий мыши и клавиатуры
        self.canvas.mpl_connect('button_press_event', self.on_chart_click)
        self.canvas.mpl_connect('button_release_event', self.on_chart_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_chart_motion)
        self.canvas.mpl_connect('scroll_event', self.on_chart_scroll)
        self.canvas.mpl_connect('key_press_event', self.on_chart_key)
        
        # Переменные для панорамирования
        self.pan_start = None
        self.is_panning = False
        
        # Настройка селектора области для зума
        self.setup_rectangle_selector()
        
        # Включение фокуса для клавиатурных событий
        self.canvas.get_tk_widget().focus_set()
    
    def on_chart_click(self, event):
        """Обработка кликов по графику"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if event.inaxes in [self.ax_price, self.ax_volume, self.ax_indicators]:
            if event.dblclick and event.inaxes == self.ax_price:
                # Двойной клик для добавления уровня
                price = event.ydata
                if price:
                    self.add_manual_level(price)
            elif event.button == 1:  # Левая кнопка мыши
                # Начало панорамирования
                self.pan_start = (event.xdata, event.ydata)
                self.is_panning = True
                self.canvas.get_tk_widget().config(cursor="fleur")
            elif event.button == 3:  # Правая кнопка мыши
                # Контекстное меню или быстрый зум
                self.show_chart_context_menu(event)
    
    def on_chart_release(self, event):
        """Обработка отпускания кнопки мыши"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if event.button == 1:  # Левая кнопка мыши
            self.is_panning = False
            self.pan_start = None
            self.canvas.get_tk_widget().config(cursor="")
    
    def on_chart_motion(self, event):
        """Обработка движения мыши"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        # Панорамирование
        if self.is_panning and self.pan_start and event.inaxes:
            if event.xdata and event.ydata:
                dx = event.xdata - self.pan_start[0]
                dy = event.ydata - self.pan_start[1]
                
                # Применение панорамирования к текущей оси
                xlim = event.inaxes.get_xlim()
                ylim = event.inaxes.get_ylim()
                
                event.inaxes.set_xlim(xlim[0] - dx, xlim[1] - dx)
                event.inaxes.set_ylim(ylim[0] - dy, ylim[1] - dy)
                
                self.canvas.draw_idle()
        
        # Отображение координат в статусной строке
        if event.inaxes and event.xdata and event.ydata:
            self.update_status_bar(event.xdata, event.ydata, event.inaxes)
    
    def on_chart_scroll(self, event):
        """Обработка прокрутки для масштабирования"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if event.inaxes in [self.ax_price, self.ax_volume, self.ax_indicators]:
            # Определение направления и силы масштабирования
            if event.step > 0:
                scale_factor = 0.9  # Приближение
            else:
                scale_factor = 1.1  # Отдаление
            
            # Получение текущих границ
            xlim = event.inaxes.get_xlim()
            ylim = event.inaxes.get_ylim()
            
            # Масштабирование относительно позиции курсора
            if event.xdata and event.ydata:
                # Масштабирование по X (время)
                x_center = event.xdata
                x_range = (xlim[1] - xlim[0]) * scale_factor / 2
                new_xlim = (x_center - x_range, x_center + x_range)
                
                # Масштабирование по Y (цена/объем)
                y_center = event.ydata
                y_range = (ylim[1] - ylim[0]) * scale_factor / 2
                new_ylim = (y_center - y_range, y_center + y_range)
            else:
                # Масштабирование от центра
                x_center = (xlim[0] + xlim[1]) / 2
                x_range = (xlim[1] - xlim[0]) * scale_factor / 2
                new_xlim = (x_center - x_range, x_center + x_range)
                
                y_center = (ylim[0] + ylim[1]) / 2
                y_range = (ylim[1] - ylim[0]) * scale_factor / 2
                new_ylim = (y_center - y_range, y_center + y_range)
            
            # Применение новых границ
            event.inaxes.set_xlim(new_xlim)
            event.inaxes.set_ylim(new_ylim)
            
            self.canvas.draw_idle()
    
    def on_chart_key(self, event):
        """Обработка клавиш"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if event.key == 'r':  # Reset zoom
            self.reset_chart_zoom()
        elif event.key == 'g':  # Toggle grid
            self.toggle_grid()
        elif event.key == 'h':  # Home (fit all data)
            self.fit_chart_to_data()
        elif event.key == 'ctrl+z':  # Undo zoom
            self.undo_zoom()
        elif event.key == 'ctrl+y':  # Redo zoom
            self.redo_zoom()
        elif event.key == 'left':  # Pan left
            self.pan_chart('left')
        elif event.key == 'right':  # Pan right
            self.pan_chart('right')
        elif event.key == 'up':  # Pan up
            self.pan_chart('up')
        elif event.key == 'down':  # Pan down
            self.pan_chart('down')
        elif event.key == 'escape':  # Cancel selection
            self.cancel_selection()
    
    def add_manual_level(self, price):
        """Добавление ручного уровня"""
        if not MATPLOTLIB_AVAILABLE:
            return
        self.ax_price.axhline(y=price, color='yellow', linestyle=':', alpha=0.8, linewidth=2)
        self.canvas.draw()
        self.log_message(f"Добавлен ручной уровень: ${price:.2f}", "SUCCESS")
    
    def reset_chart_zoom(self):
        """Сброс масштабирования"""
        if not MATPLOTLIB_AVAILABLE:
            return""
        for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
            ax.relim()
            ax.autoscale()
        self.canvas.draw()
    
    def toggle_grid(self):
        """Переключение сетки"""
        if not MATPLOTLIB_AVAILABLE:
            return
        for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
            ax.grid(not ax.get_gridlines()[0].get_visible() if ax.get_gridlines() else True, 
                   alpha=self.chart_settings['grid_alpha'])
        self.canvas.draw_idle()
    
    def setup_rectangle_selector(self):
        """Настройка селектора прямоугольной области для зума"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        from matplotlib.widgets import RectangleSelector
        
        def onselect(eclick, erelease):
            """Обработка выделения области для зума"""
            if eclick.inaxes and erelease.inaxes:
                # Получение координат выделенной области
                x1, x2 = sorted([eclick.xdata, erelease.xdata])
                y1, y2 = sorted([eclick.ydata, erelease.ydata])
                
                # Применение зума к выделенной области
                eclick.inaxes.set_xlim(x1, x2)
                eclick.inaxes.set_ylim(y1, y2)
                
                # Синхронизация X-оси для всех графиков
                for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
                    if ax != eclick.inaxes:
                        ax.set_xlim(x1, x2)
                
                self.canvas.draw_idle()
                self.save_zoom_state()
        
        # Создание селекторов для каждого графика
        self.rect_selector_price = RectangleSelector(
            self.ax_price, onselect, useblit=True,
            button=[1], minspanx=5, minspany=5,
            spancoords='pixels', interactive=False
        )
        
        self.rect_selector_volume = RectangleSelector(
            self.ax_volume, onselect, useblit=True,
            button=[1], minspanx=5, minspany=5,
            spancoords='pixels', interactive=False
        )
        
        self.rect_selector_indicators = RectangleSelector(
            self.ax_indicators, onselect, useblit=True,
            button=[1], minspanx=5, minspany=5,
            spancoords='pixels', interactive=False
        )
        
        # Изначально отключаем селекторы
        self.rect_selector_price.set_active(False)
        self.rect_selector_volume.set_active(False)
        self.rect_selector_indicators.set_active(False)
    
    def show_chart_context_menu(self, event):
        """Показ контекстного меню графика"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        # Создание контекстного меню
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="🔍 Включить зум-селектор", command=self.toggle_zoom_selector)
        context_menu.add_command(label="🏠 Показать все данные", command=self.fit_chart_to_data)
        context_menu.add_command(label="↺ Сбросить зум", command=self.reset_chart_zoom)
        context_menu.add_separator()
        context_menu.add_command(label="📏 Добавить уровень", command=lambda: self.add_manual_level(event.ydata) if event.ydata else None)
        context_menu.add_command(label="🎨 Настройки графика", command=self.open_chart_settings)
        
        # Показ меню в позиции курсора
        try:
            context_menu.tk_popup(event.guiEvent.x_root, event.guiEvent.y_root)
        except:
            pass
        finally:
            context_menu.grab_release()
    
    def toggle_zoom_selector(self):
        """Переключение режима выделения области для зума"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        # Переключение активности селекторов
        active = not self.rect_selector_price.active
        self.rect_selector_price.set_active(active)
        self.rect_selector_volume.set_active(active)
        self.rect_selector_indicators.set_active(active)
        
        # Изменение курсора
        cursor = "crosshair" if active else ""
        self.canvas.get_tk_widget().config(cursor=cursor)
        
        # Уведомление пользователя
        status = "включен" if active else "выключен"
        self.log_message(f"Режим выделения области {status}", "INFO")
    
    def fit_chart_to_data(self):
        """Подгонка графика под все данные"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
            ax.relim()
            ax.autoscale()
        
        self.canvas.draw_idle()
        self.save_zoom_state()
    
    def pan_chart(self, direction):
        """Панорамирование графика в указанном направлении"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        pan_factor = 0.1  # 10% от текущего диапазона
        
        for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            
            if direction == 'left':
                x_shift = -(xlim[1] - xlim[0]) * pan_factor
                ax.set_xlim(xlim[0] + x_shift, xlim[1] + x_shift)
            elif direction == 'right':
                x_shift = (xlim[1] - xlim[0]) * pan_factor
                ax.set_xlim(xlim[0] + x_shift, xlim[1] + x_shift)
            elif direction == 'up':
                y_shift = (ylim[1] - ylim[0]) * pan_factor
                ax.set_ylim(ylim[0] + y_shift, ylim[1] + y_shift)
            elif direction == 'down':
                y_shift = -(ylim[1] - ylim[0]) * pan_factor
                ax.set_ylim(ylim[0] + y_shift, ylim[1] + y_shift)
        
        self.canvas.draw_idle()
    
    def cancel_selection(self):
        """Отмена текущего выделения"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        # Отключение селекторов
        self.rect_selector_price.set_active(False)
        self.rect_selector_volume.set_active(False)
        self.rect_selector_indicators.set_active(False)
        
        # Сброс курсора
        self.canvas.get_tk_widget().config(cursor="")
    
    def update_status_bar(self, x, y, axes):
        """Обновление статусной строки с координатами"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        # Определение типа графика
        if axes == self.ax_price:
            chart_type = "Цена"
            y_label = f"${y:.2f}"
        elif axes == self.ax_volume:
            chart_type = "Объем"
            y_label = f"{y:.0f}"
        else:
            chart_type = "Индикаторы"
            y_label = f"{y:.2f}"
        
        # Форматирование времени (если x - это время)
        try:
            if hasattr(self, 'df') and self.df is not None and len(self.df) > 0:
                time_label = f"Индекс: {int(x)}"
            else:
                time_label = f"X: {x:.2f}"
        except:
            time_label = f"X: {x:.2f}"
        
        # Обновление статуса (если есть статусная строка)
        status_text = f"{chart_type} | {time_label} | {y_label}"
        # Здесь можно добавить обновление статусной строки, если она существует
    
    def save_zoom_state(self):
        """Сохранение текущего состояния зума для истории"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if not hasattr(self, 'zoom_history'):
            self.zoom_history = []
            self.zoom_index = -1
        
        # Сохранение текущих границ всех осей
        state = {
            'price': self.ax_price.get_xlim() + self.ax_price.get_ylim(),
            'volume': self.ax_volume.get_xlim() + self.ax_volume.get_ylim(),
            'indicators': self.ax_indicators.get_xlim() + self.ax_indicators.get_ylim()
        }
        
        # Добавление в историю
        self.zoom_history = self.zoom_history[:self.zoom_index + 1]
        self.zoom_history.append(state)
        self.zoom_index = len(self.zoom_history) - 1
        
        # Ограничение размера истории
        if len(self.zoom_history) > 20:
            self.zoom_history.pop(0)
            self.zoom_index -= 1
    
    def undo_zoom(self):
        """Отмена последнего зума"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if hasattr(self, 'zoom_history') and self.zoom_index > 0:
            self.zoom_index -= 1
            self.restore_zoom_state(self.zoom_history[self.zoom_index])
    
    def redo_zoom(self):
        """Повтор отмененного зума"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if hasattr(self, 'zoom_history') and self.zoom_index < len(self.zoom_history) - 1:
            self.zoom_index += 1
            self.restore_zoom_state(self.zoom_history[self.zoom_index])
    
    def restore_zoom_state(self, state):
        """Восстановление состояния зума"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        try:
            # Восстановление границ для каждой оси
            self.ax_price.set_xlim(state['price'][0], state['price'][1])
            self.ax_price.set_ylim(state['price'][2], state['price'][3])
            
            self.ax_volume.set_xlim(state['volume'][0], state['volume'][1])
            self.ax_volume.set_ylim(state['volume'][2], state['volume'][3])
            
            self.ax_indicators.set_xlim(state['indicators'][0], state['indicators'][1])
            self.ax_indicators.set_ylim(state['indicators'][2], state['indicators'][3])
            
            self.canvas.draw_idle()
        except Exception as e:
            self.log_message(f"Ошибка восстановления зума: {e}", "ERROR")
    
    def open_chart_settings(self):
        """Открытие окна настроек графика"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("🎨 Настройки графика")
        settings_window.geometry("400x500")
        settings_window.configure(bg='#1e1e1e')
        
        # Цвета
        color_frame = ttk.LabelFrame(settings_window, text="Цветовая схема", padding=10)
        color_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(color_frame, text="Цвет поддержки", 
                  command=lambda: self.choose_color('support_color')).pack(fill=tk.X, pady=2)
        ttk.Button(color_frame, text="Цвет сопротивления", 
                  command=lambda: self.choose_color('resistance_color')).pack(fill=tk.X, pady=2)
        ttk.Button(color_frame, text="Фон графика", 
                  command=lambda: self.choose_color('background_color')).pack(fill=tk.X, pady=2)
        
        # Прозрачность
        alpha_frame = ttk.LabelFrame(settings_window, text="Прозрачность", padding=10)
        alpha_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(alpha_frame, text="Зоны:").pack(anchor=tk.W)
        zone_alpha_scale = ttk.Scale(alpha_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                    value=self.chart_settings['zone_alpha'])
        zone_alpha_scale.pack(fill=tk.X)
        zone_alpha_scale.configure(command=lambda v: self.update_setting('zone_alpha', float(v)))
        
        ttk.Label(alpha_frame, text="Сетка:").pack(anchor=tk.W)
        grid_alpha_scale = ttk.Scale(alpha_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                    value=self.chart_settings['grid_alpha'])
        grid_alpha_scale.pack(fill=tk.X)
        grid_alpha_scale.configure(command=lambda v: self.update_setting('grid_alpha', float(v)))
        
        # Кнопки действий
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Применить", command=self.apply_chart_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сброс", command=self.reset_chart_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сохранить", command=self.save_settings).pack(side=tk.LEFT, padx=5)
    
    def choose_color(self, setting_key):
        """Выбор цвета"""
        color = colorchooser.askcolor(title=f"Выберите цвет для {setting_key}")
        if color[1]:  # Если цвет выбран
            self.chart_settings[setting_key] = color[1]
            self.apply_chart_settings()
    
    def update_setting(self, key, value):
        """Обновление настройки"""
        self.chart_settings[key] = value
    
    def apply_chart_settings(self):
        """Применение настроек графика"""
        # Обновление цветов фона
        for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
            ax.set_facecolor(self.chart_settings['background_color'])
        
        # Перерисовка графика
        self.update_chart()
        self.log_message("Настройки графика применены", "SUCCESS")
    
    def reset_chart_settings(self):
        """Сброс настроек графика"""
        self.chart_settings = {
            'support_color': '#00ff88',
            'resistance_color': '#ff4444',
            'background_color': '#2d2d2d',
            'grid_alpha': 0.3,
            'zone_alpha': 0.4,
            'show_volume': True,
            'show_indicators': True,
            'chart_style': 'dark'
        }
        self.apply_chart_settings()
    
    def open_ml_settings(self):
        """Открытие окна настроек ML"""
        ml_window = tk.Toplevel(self.root)
        ml_window.title("🤖 Настройки ML моделей")
        ml_window.geometry("500x600")
        ml_window.configure(bg='#1e1e1e')
        
        # Выбор модели
        model_frame = ttk.LabelFrame(ml_window, text="Модели машинного обучения", padding=10)
        model_frame.pack(fill=tk.X, padx=10, pady=5)
        
        for model_name in ['RandomForest', 'GradientBoosting', 'NeuralNetwork', 'SVM']:
            frame = ttk.Frame(model_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=model_name).pack(side=tk.LEFT)
            
            if model_name in self.model_performance:
                accuracy = self.model_performance[model_name].get('accuracy', 0)
                ttk.Label(frame, text=f"Точность: {accuracy:.2%}").pack(side=tk.RIGHT)
        
        # Параметры индикаторов
        indicators_frame = ttk.LabelFrame(ml_window, text="Технические индикаторы", padding=10)
        indicators_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # RSI период
        ttk.Label(indicators_frame, text="RSI период:").pack(anchor=tk.W)
        rsi_scale = ttk.Scale(indicators_frame, from_=5, to=30, orient=tk.HORIZONTAL,
                             value=self.indicators['rsi_period'])
        rsi_scale.pack(fill=tk.X)
        rsi_scale.configure(command=lambda v: self.update_indicator('rsi_period', int(float(v))))
        
        # Кнопки
        button_frame = ttk.Frame(ml_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Переобучить все модели", 
                  command=self.retrain_all_models).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Экспорт моделей", 
                  command=self.export_models).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Импорт моделей", 
                  command=self.import_models).pack(fill=tk.X, pady=2)
    
    def update_indicator(self, key, value):
        """Обновление параметров индикаторов"""
        self.indicators[key] = value
    
    def on_model_change(self, event=None):
        """Обработка смены модели"""
        self.current_model = self.model_var.get()
        self.log_message(f"Выбрана модель: {self.current_model}", "SUCCESS")
        self.update_position_info()  # Обновить ML сигнал
    
    def save_settings(self):
        """Сохранение настроек"""
        try:
            settings = {
                'chart_settings': self.chart_settings,
                'indicators': self.indicators,
                'current_model': self.current_model
            }
            
            with open('bot_settings.pkl', 'wb') as f:
                pickle.dump(settings, f)
            
            self.log_message("Настройки сохранены", "SUCCESS")
        except Exception as e:
            self.log_message(f"Ошибка сохранения настроек: {e}", "ERROR")
    
    def load_settings(self):
        """Загрузка настроек"""
        try:
            if os.path.exists('bot_settings.pkl'):
                with open('bot_settings.pkl', 'rb') as f:
                    settings = pickle.load(f)
                
                self.chart_settings.update(settings.get('chart_settings', {}))
                self.indicators.update(settings.get('indicators', {}))
                self.current_model = settings.get('current_model', 'RandomForest')
                
                self.log_message("Настройки загружены", "SUCCESS")
        except Exception as e:
            self.log_message(f"Ошибка загрузки настроек: {e}", "ERROR")
    
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
        """Настройка множественных ML моделей для предсказания направления цены"""
        if not SKLEARN_AVAILABLE:
            return
            
        try:
            # Инициализация множественных моделей
            self.ml_models = {
                'RandomForest': RandomForestClassifier(
                    n_estimators=200,
                    max_depth=15,
                    min_samples_split=5,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=-1
                ),
                'GradientBoosting': GradientBoostingClassifier(
                    n_estimators=150,
                    learning_rate=0.1,
                    max_depth=8,
                    random_state=42
                ),
                'NeuralNetwork': MLPClassifier(
                    hidden_layer_sizes=(100, 50, 25),
                    activation='relu',
                    solver='adam',
                    alpha=0.001,
                    learning_rate='adaptive',
                    max_iter=500,
                    random_state=42
                ),
                'SVM': SVC(
                    kernel='rbf',
                    C=1.0,
                    gamma='scale',
                    probability=True,
                    random_state=42
                )
            }
            
            # Используем RobustScaler для лучшей обработки выбросов
            self.scaler = RobustScaler()
            self.model_performance = {}
            
            # Устанавливаем модель по умолчанию
            self.ml_model = self.ml_models[self.current_model]
            
            self.log_message("Множественные ML модели инициализированы", "SUCCESS")
        except Exception as e:
            self.log_message(f"Ошибка инициализации ML моделей: {e}", "ERROR")
    
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
        """Оптимизированное обучение ML модели"""
        if not SKLEARN_AVAILABLE or df is None or len(df) < 50:
            return
        
        # Кэширование для предотвращения повторного обучения
        data_signature = hash(str(df.tail(50).values.tobytes()) + self.current_model)
        if data_signature in self.ml_cache:
            return
        
        def train_async():
            try:
                features, targets = self.prepare_ml_features(df)
                if features is None or len(features) < 20:
                    return
                
                # Разделение на обучающую и тестовую выборки
                X_train, X_test, y_train, y_test = train_test_split(
                    features, targets, test_size=0.2, random_state=42, stratify=targets
                )
                
                # Нормализация признаков
                X_train_scaled = self.scaler.fit_transform(X_train)
                X_test_scaled = self.scaler.transform(X_test)
                
                # Обучение текущей модели
                current_model = self.ml_models[self.current_model]
                current_model.fit(X_train_scaled, y_train)
                
                # Оценка производительности (упрощенная)
                test_accuracy = current_model.score(X_test_scaled, y_test)
                
                # Быстрая кросс-валидация (меньше фолдов)
                cv_scores = cross_val_score(current_model, X_train_scaled, y_train, cv=3)
                
                # Сохранение результатов
                self.model_performance[self.current_model] = {
                    'test_accuracy': test_accuracy,
                    'cv_mean': cv_scores.mean(),
                    'cv_std': cv_scores.std(),
                    'accuracy': test_accuracy
                }
                
                # Обновление основной модели
                self.ml_model = current_model
                
                # Кэширование результата
                self.ml_cache[data_signature] = True
                
                # Логирование в основном потоке
                self.root.after(0, lambda: self.log_message(
                    f"Модель {self.current_model} обучена. Тест: {test_accuracy*100:.2f}%, CV: {cv_scores.mean()*100:.2f}%±{cv_scores.std()*100:.2f}%", 
                    "SUCCESS"
                ))
                
            except Exception as e:
                error_msg = str(e)  # Сохраняем сообщение об ошибке в переменную
                self.root.after(0, lambda error=error_msg: self.log_message(f"Ошибка обучения ML модели: {error}", "ERROR"))
        
        # Запуск обучения в отдельном потоке
        threading.Thread(target=train_async, daemon=True).start()
    
    def retrain_all_models(self):
        """Переобучение всех моделей"""
        if not hasattr(self, 'df') or self.df is None:
            self.log_message("Нет данных для обучения", "WARNING")
            return
        
        original_model = self.current_model
        
        for model_name in self.ml_models.keys():
            self.current_model = model_name
            self.train_ml_model(self.df)
        
        self.current_model = original_model
        self.ml_model = self.ml_models[self.current_model]
        
        self.log_message("Все модели переобучены", "SUCCESS")
    
    def export_models(self):
        """Экспорт обученных моделей"""
        try:
            models_data = {
                'models': self.ml_models,
                'scaler': self.scaler,
                'performance': self.model_performance,
                'current_model': self.current_model
            }
            
            with open('trained_models.pkl', 'wb') as f:
                pickle.dump(models_data, f)
            
            self.log_message("Модели экспортированы в trained_models.pkl", "SUCCESS")
        except Exception as e:
            self.log_message(f"Ошибка экспорта моделей: {e}", "ERROR")
    
    def import_models(self):
        """Импорт обученных моделей"""
        try:
            if os.path.exists('trained_models.pkl'):
                with open('trained_models.pkl', 'rb') as f:
                    models_data = pickle.load(f)
                
                self.ml_models = models_data['models']
                self.scaler = models_data['scaler']
                self.model_performance = models_data.get('performance', {})
                self.current_model = models_data.get('current_model', 'RandomForest')
                self.ml_model = self.ml_models[self.current_model]
                
                self.log_message("Модели импортированы из trained_models.pkl", "SUCCESS")
            else:
                self.log_message("Файл trained_models.pkl не найден", "WARNING")
        except Exception as e:
            self.log_message(f"Ошибка импорта моделей: {e}", "ERROR")
    
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
        """Оптимизированное обновление графика"""
        if not MATPLOTLIB_AVAILABLE or self.df is None or len(self.df) == 0:
            return
        
        # Проверка на частые обновления
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return
        
        if self.is_updating:
            return
            
        self.is_updating = True
        
        try:
            # Кэширование данных для графика
            data_hash = hash(str(self.df.iloc[-10:].values.tobytes()) + str(self.chart_settings))
            if data_hash in self.chart_cache:
                self.is_updating = False
                return
            
            # Очистка графиков
            self.ax_price.clear()
            if self.chart_settings['show_volume']:
                self.ax_volume.clear()
            if self.chart_settings['show_indicators']:
                self.ax_indicators.clear()
            
            # Применение настроек фона
            for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
                ax.set_facecolor(self.chart_settings['background_color'])
            
            # Оптимизированная отрисовка свечей (векторизованная)
            df_subset = self.df.tail(200)  # Показываем только последние 200 свечей
            
            # Подготовка данных для быстрой отрисовки
            opens = df_subset['open'].values
            highs = df_subset['high'].values
            lows = df_subset['low'].values
            closes = df_subset['close'].values
            indices = range(len(df_subset))
            
            # Векторизованная отрисовка свечей
            colors = ['#00ff88' if c > o else '#ff4444' for c, o in zip(closes, opens)]
            
            # Тела свечей
            body_heights = np.abs(closes - opens)
            body_bottoms = np.minimum(opens, closes)
            
            self.ax_price.bar(indices, body_heights, bottom=body_bottoms, 
                            width=0.8, color=colors, alpha=0.8, 
                            edgecolor='white', linewidth=0.3)
            
            # Тени свечей (оптимизированно)
            for i, (h, l, c) in enumerate(zip(highs, lows, colors)):
                self.ax_price.plot([i, i], [l, h], color=c, linewidth=1, alpha=0.7)
            
            # Зоны плотности с настраиваемыми цветами
            if hasattr(self, 'density_zones') and self.density_zones:
                for zone in self.density_zones:
                    zone_type = zone.get('type', 'support')
                    color = (self.chart_settings['support_color'] if zone_type == 'support' 
                            else self.chart_settings['resistance_color'])
                    
                    # Зона как прямоугольник
                    y_min = zone['center'] - zone['width']
                    y_max = zone['center'] + zone['width']
                    
                    self.ax_price.axhspan(y_min, y_max, alpha=self.chart_settings['zone_alpha'], 
                                        color=color, label=f"{zone_type.title()} (Сила: {zone.get('strength', 1):.1f})")
                    
                    # Центральная линия зоны
                    self.ax_price.axhline(y=zone['center'], color=color, 
                                        linestyle='--', alpha=0.8, linewidth=1.5)
                    
                    # Подпись зоны
                    zone_label = f"{zone_type[:3].upper()}: ${zone['center']:.2f}"
                    self.ax_price.text(len(self.df)-20, zone['center'], zone_label,
                                     color=color, fontsize=9, fontweight='bold',
                                     bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
            
            # Технические индикаторы
            if self.chart_settings['show_indicators'] and len(self.df) > 20:
                # RSI
                rsi_values = []
                for i in range(len(self.df)):
                    if i >= self.indicators['rsi_period']:
                        rsi = self.calculate_rsi(self.df['close'].iloc[:i+1], self.indicators['rsi_period'])
                        rsi_values.append(rsi)
                    else:
                        rsi_values.append(50)  # Нейтральное значение
                
                self.ax_indicators.plot(range(len(rsi_values)), rsi_values, 
                                      color='#ffaa00', linewidth=2, label='RSI')
                self.ax_indicators.axhline(y=70, color='red', linestyle='--', alpha=0.7, label='Перекупленность')
                self.ax_indicators.axhline(y=30, color='green', linestyle='--', alpha=0.7, label='Перепроданность')
                self.ax_indicators.axhline(y=50, color='gray', linestyle='-', alpha=0.5)
                self.ax_indicators.set_ylim(0, 100)
                self.ax_indicators.set_ylabel('RSI', color='white', fontweight='bold')
                self.ax_indicators.legend(loc='upper right', facecolor='#1e1e1e', edgecolor='white')
            
            # График объемов с улучшенным отображением
            if self.chart_settings['show_volume']:
                colors = ['#00ff88' if close > open_price else '#ff4444' 
                         for close, open_price in zip(self.df['close'], self.df['open'])]
                
                self.ax_volume.bar(range(len(self.df)), self.df['volume'], 
                                 color=colors, alpha=0.7, edgecolor='white', linewidth=0.3)
                
                # Средний объем
                if len(self.df) > 20:
                    avg_volume = self.df['volume'].rolling(20).mean()
                    self.ax_volume.plot(range(len(avg_volume)), avg_volume, 
                                      color='yellow', linewidth=2, alpha=0.8, label='Средний объем (20)')
                    self.ax_volume.legend(loc='upper right', facecolor='#1e1e1e', edgecolor='white')
            
            # Текущая позиция с дополнительной информацией
            if hasattr(self, 'position_size') and self.position_size != 0:
                entry_price = getattr(self, 'entry_price', 0)
                if entry_price > 0:
                    current_price = self.df['close'].iloc[-1]
                    pnl_pct = ((current_price / entry_price - 1) * 100 * 
                              (1 if self.position_size > 0 else -1))
                    
                    color = '#00ff88' if self.position_size > 0 else '#ff4444'
                    self.ax_price.axhline(y=entry_price, color=color, 
                                        linestyle='-', linewidth=3, alpha=0.9,
                                        label=f'Позиция: ${entry_price:.2f} ({pnl_pct:+.2f}%)')
            
            # Настройка осей с улучшенным форматированием
            current_price = self.df['close'].iloc[-1]
            price_change = ((current_price / self.df['close'].iloc[-2] - 1) * 100) if len(self.df) > 1 else 0
            
            self.ax_price.set_title(
                f'📈 {self.symbol_var.get()} - {self.interval_var.get()} | '
                f'Цена: ${current_price:.2f} | '
                f'Изменение: {price_change:+.2f}% | '
                f'Объем: {self.df["volume"].iloc[-1]:,.0f}',
                color='white', fontsize=11, fontweight='bold'
            )
            
            self.ax_price.set_ylabel('Цена (USDT)', color='white', fontweight='bold')
            if self.chart_settings['show_volume']:
                self.ax_volume.set_ylabel('Объем', color='white', fontweight='bold')
            if self.chart_settings['show_indicators']:
                self.ax_indicators.set_xlabel('Время', color='white', fontweight='bold')
            
            # Цвета осей и сетка
            for ax in [self.ax_price, self.ax_volume, self.ax_indicators]:
                ax.tick_params(colors='white', labelsize=9)
                for spine in ax.spines.values():
                    spine.set_color('white')
                    spine.set_linewidth(1.2)
                ax.grid(True, alpha=self.chart_settings['grid_alpha'], 
                       color='white', linestyle=':')
            
            # Легенда с улучшенным стилем
            if hasattr(self, 'density_zones') and self.density_zones:
                legend = self.ax_price.legend(loc='upper left', fancybox=True, 
                                            framealpha=0.9, fontsize=8,
                                            facecolor='#1e1e1e', edgecolor='white')
                for text in legend.get_texts():
                    text.set_color('white')
            
            # Форматирование времени на оси X
            if len(self.df) > 0:
                time_labels = []
                tick_positions = list(range(0, len(self.df), max(1, len(self.df)//10)))
                
                for pos in tick_positions:
                    if 'timestamp' in self.df.columns:
                        time_labels.append(pd.to_datetime(self.df['timestamp'].iloc[pos], unit='ms').strftime('%H:%M'))
                    else:
                        time_labels.append(f'{pos}')
                
                self.ax_price.set_xticks(tick_positions)
                self.ax_price.set_xticklabels(time_labels, rotation=45)
            
            # Сохранение в кэш и финализация
            self.chart_cache[data_hash] = True
            self.last_update_time = current_time
            
            # Оптимизированная отрисовка
            self.canvas.draw_idle()
            
        except Exception as e:
            self.log_message(f"Ошибка обновления графика: {e}", "ERROR")
        finally:
            self.is_updating = False
    
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
        """Оптимизированная обработка сообщений WebSocket"""
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
                # Асинхронное обновление интерфейса
                self.root.after_idle(self.update_orderbook_display)
                
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
        """Обновление информации о позиции с расширенной статистикой"""
        try:
            # Очистка предыдущей информации
            for widget in self.position_frame.winfo_children():
                widget.destroy()
            
            # Заголовок с временем
            current_time = pd.Timestamp.now().strftime('%H:%M:%S')
            header_label = tk.Label(self.position_frame, 
                                  text=f"📊 Позиция | {current_time}", 
                                  bg='#1e1e1e', fg='white', font=('Arial', 11, 'bold'))
            header_label.pack(pady=2)
            
            # Баланс с изменением
            balance_change = getattr(self, 'balance_change', 0)
            balance_color = '#00ff88' if balance_change > 0 else '#ff4444' if balance_change < 0 else 'white'
            balance_text = f"💰 Баланс: ${self.balance:.2f}"
            if balance_change != 0:
                balance_text += f" ({balance_change:+.2f})"
            
            balance_label = tk.Label(self.position_frame, text=balance_text, 
                                   bg='#1e1e1e', fg=balance_color, font=('Arial', 10, 'bold'))
            balance_label.pack(pady=1)
            
            # Текущая цена с изменением
            if hasattr(self, 'df') and self.df is not None and len(self.df) > 1:
                current_price = self.df['close'].iloc[-1]
                prev_price = self.df['close'].iloc[-2]
                price_change = current_price - prev_price
                price_change_pct = (price_change / prev_price) * 100
                
                price_color = '#00ff88' if price_change > 0 else '#ff4444' if price_change < 0 else 'white'
                price_label = tk.Label(self.position_frame, 
                                     text=f"💲 Цена: ${current_price:.2f} ({price_change_pct:+.2f}%)", 
                                     bg='#1e1e1e', fg=price_color, font=('Arial', 10))
                price_label.pack(pady=1)
            
            # Размер позиции с детальной информацией
            position_color = '#00ff88' if self.position_size > 0 else '#ff4444' if self.position_size < 0 else 'white'
            position_type = "LONG" if self.position_size > 0 else "SHORT" if self.position_size < 0 else "НЕТ"
            
            position_text = f"📈 Позиция: {position_type}"
            if self.position_size != 0:
                position_value = abs(self.position_size * getattr(self, 'entry_price', 0))
                position_text += f" | {abs(self.position_size):.4f} (${position_value:.2f})"
            
            position_label = tk.Label(self.position_frame, text=position_text, 
                                    bg='#1e1e1e', fg=position_color, font=('Arial', 10, 'bold'))
            position_label.pack(pady=1)
            
            # Цена входа
            if self.position_size != 0 and hasattr(self, 'entry_price'):
                entry_label = tk.Label(self.position_frame, 
                                     text=f"🎯 Вход: ${self.entry_price:.2f}", 
                                     bg='#1e1e1e', fg='yellow', font=('Arial', 9))
                entry_label.pack(pady=1)
            
            # P&L с детальной информацией
            if self.position_size != 0 and hasattr(self, 'df') and self.df is not None and hasattr(self, 'entry_price'):
                current_price = self.df['close'].iloc[-1]
                pnl = (current_price - self.entry_price) * self.position_size
                pnl_pct = (pnl / (abs(self.position_size) * self.entry_price)) * 100
                
                # Общий P&L
                total_pnl = getattr(self, 'total_pnl', 0) + pnl
                
                pnl_color = '#00ff88' if pnl > 0 else '#ff4444'
                pnl_label = tk.Label(self.position_frame, 
                                    text=f"💹 P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)", 
                                    bg='#1e1e1e', fg=pnl_color, font=('Arial', 10, 'bold'))
                pnl_label.pack(pady=1)
                
                # Общий P&L за сессию
                total_pnl_color = '#00ff88' if total_pnl > 0 else '#ff4444' if total_pnl < 0 else 'white'
                total_pnl_label = tk.Label(self.position_frame, 
                                         text=f"📊 Общий P&L: ${total_pnl:.2f}", 
                                         bg='#1e1e1e', fg=total_pnl_color, font=('Arial', 9))
                total_pnl_label.pack(pady=1)
            
            # Разделитель
            separator = tk.Frame(self.position_frame, height=1, bg='#555555')
            separator.pack(fill=tk.X, pady=3)
            
            # ML модель и точность
            if hasattr(self, 'current_model') and hasattr(self, 'model_performance'):
                model_accuracy = self.model_performance.get(self.current_model, {}).get('test_accuracy', 0)
                accuracy_color = '#00ff88' if model_accuracy > 0.6 else '#ffaa00' if model_accuracy > 0.5 else '#ff4444'
                
                model_label = tk.Label(self.position_frame, 
                                     text=f"🤖 Модель: {self.current_model}", 
                                     bg='#1e1e1e', fg='white', font=('Arial', 9))
                model_label.pack(pady=1)
                
                accuracy_label = tk.Label(self.position_frame, 
                                         text=f"🎯 Точность: {model_accuracy:.1%}", 
                                         bg='#1e1e1e', fg=accuracy_color, font=('Arial', 9))
                accuracy_label.pack(pady=1)
            
            # ML сигнал с уверенностью
            if self.df is not None:
                ml_signal = self.get_ml_prediction(self.df)
                confidence = getattr(self, 'last_ml_confidence', 0.5)
                signal_color = '#00ff88' if ml_signal == 'BUY' else '#ff4444' if ml_signal == 'SELL' else 'yellow'
                
                signal_label = tk.Label(self.position_frame, 
                                       text=f"🚦 Сигнал: {ml_signal} ({confidence:.1%})", 
                                       bg='#1e1e1e', fg=signal_color, font=('Arial', 9, 'bold'))
                signal_label.pack(pady=1)
            
            # Статистика торговли
            trades_count = getattr(self, 'trades_count', 0)
            win_rate = getattr(self, 'win_rate', 0)
            
            if trades_count > 0:
                stats_label = tk.Label(self.position_frame, 
                                      text=f"📈 Сделок: {trades_count} | Винрейт: {win_rate:.1%}", 
                                      bg='#1e1e1e', fg='#cccccc', font=('Arial', 8))
                stats_label.pack(pady=1)
            
            # Индикаторы состояния
            status_frame = tk.Frame(self.position_frame, bg='#1e1e1e')
            status_frame.pack(fill=tk.X, pady=2)
            
            # Автоторговля
            auto_status = "🟢 ВКЛ" if getattr(self, 'auto_trading', False) else "🔴 ВЫКЛ"
            auto_color = '#00ff88' if getattr(self, 'auto_trading', False) else '#ff4444'
            auto_label = tk.Label(status_frame, text=f"Авто: {auto_status}", 
                                bg='#1e1e1e', fg=auto_color, font=('Arial', 8))
            auto_label.pack(side=tk.LEFT, padx=2)
            
            # WebSocket статус
            ws_status = "🟢 ОК" if getattr(self, 'websocket_connected', False) else "🔴 НЕТ"
            ws_color = '#00ff88' if getattr(self, 'websocket_connected', False) else '#ff4444'
            ws_label = tk.Label(status_frame, text=f"WS: {ws_status}", 
                              bg='#1e1e1e', fg=ws_color, font=('Arial', 8))
            ws_label.pack(side=tk.RIGHT, padx=2)
                
        except Exception as e:
            self.log_message(f"Ошибка обновления информации: {e}", "ERROR")
    
    def update_data(self):
        """Оптимизированное обновление данных"""
        try:
            # Проверка на слишком частые обновления
            current_time = time.time()
            if hasattr(self, 'last_full_update') and (current_time - self.last_full_update) < 2.0:
                return
            
            self.symbol = self.symbol_var.get()
            self.interval = self.interval_var.get()
            
            self.log_message(f"Обновление данных для {self.symbol} ({self.interval})...")
            
            # Получение новых данных
            new_df = self.get_kline_data(self.symbol, self.interval)
            
            if new_df is not None:
                # Проверка на изменения данных
                if hasattr(self, 'df') and self.df is not None and len(new_df) > 0:
                    if len(new_df) == len(self.df) and abs(new_df.iloc[-1]['close'] - self.df.iloc[-1]['close']) < 0.0001:
                        return  # Данные практически не изменились
                
                self.df = new_df
                self.last_full_update = current_time
                
                # Расчет зон плотности (реже)
                if not hasattr(self, 'last_density_calc') or (current_time - self.last_density_calc) > 10.0:
                    self.density_zones = self.calculate_density_zones(self.df)
                    self.log_message(f"Найдено {len(self.density_zones)} зон плотности")
                    self.last_density_calc = current_time
                
                # Обучение ML модели (еще реже)
                if SKLEARN_AVAILABLE and (not hasattr(self, 'last_ml_train') or (current_time - self.last_ml_train) > 60.0):
                    self.train_ml_model(self.df)
                    self.last_ml_train = current_time
                
                # Обновление графика
                self.update_chart()
                
                # Обновление информации (реже)
                if not hasattr(self, 'last_info_update') or (current_time - self.last_info_update) > 3.0:
                    self.update_position_info()
                    self.last_info_update = current_time
                
                # Проверка торговых сигналов
                self.check_trading_signals()
                
                # Перезапуск WebSocket для новой пары
                if WEBSOCKET_AVAILABLE:
                    self.start_websocket()
                
                if hasattr(self, 'status_label'):
                    self.status_label.config(text="📡 Обновлено", style='Success.TLabel')
                
            else:
                if hasattr(self, 'status_label'):
                    self.status_label.config(text="❌ Ошибка данных", style='Error.TLabel')
                
        except Exception as e:
            self.log_message(f"Ошибка обновления данных: {e}", "ERROR")
            if hasattr(self, 'status_label'):
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
    
    def create_top_controls(self):
        """Создание верхней панели с основными контролами"""
        top_frame = ttk.Frame(self.control_frame)
        top_frame.pack(fill=tk.X, pady=10)
        
        # Выбор символа и интервала
        symbol_frame = ttk.Frame(top_frame)
        symbol_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(symbol_frame, text="Символ:").pack(side=tk.LEFT, padx=5)
        self.symbol_var = tk.StringVar(value=self.settings['trading']['symbol'])
        symbol_combo = ttk.Combobox(symbol_frame, textvariable=self.symbol_var, 
                                   values=['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT'])
        symbol_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        symbol_combo.bind('<<ComboboxSelected>>', self.on_symbol_change)
        
        interval_frame = ttk.Frame(top_frame)
        interval_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(interval_frame, text="Интервал:").pack(side=tk.LEFT, padx=5)
        self.interval_var = tk.StringVar(value=self.settings['trading']['interval'])
        interval_combo = ttk.Combobox(interval_frame, textvariable=self.interval_var,
                                     values=['1m', '5m', '15m', '1h', '4h', '1d'])
        interval_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        interval_combo.bind('<<ComboboxSelected>>', self.on_interval_change)
        
        # Кнопки управления
        buttons_frame = ttk.Frame(top_frame)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        self.update_btn = ttk.Button(buttons_frame, text="Обновить данные", command=self.update_data)
        self.update_btn.pack(side=tk.LEFT, padx=5)
        
        self.auto_trading_var = tk.BooleanVar(value=self.settings['trading']['auto_trading'])
        self.auto_trading_cb = ttk.Checkbutton(buttons_frame, text="Авто-торговля", 
                                             variable=self.auto_trading_var,
                                             command=self.toggle_auto_trading)
        self.auto_trading_cb.pack(side=tk.LEFT, padx=5)
    
    def create_position_panel(self):
        """Создание панели с информацией о позиции"""
        position_frame = ttk.LabelFrame(self.control_frame, text="Позиция")
        position_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Информация о балансе
        balance_frame = ttk.Frame(position_frame)
        balance_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(balance_frame, text="Баланс:").pack(side=tk.LEFT, padx=5)
        self.balance_label = ttk.Label(balance_frame, text=f"{self.trading_manager.balance:.2f}")
        self.balance_label.pack(side=tk.LEFT, padx=5)
        
        # Информация о текущей позиции
        self.position_info_label = ttk.Label(position_frame, text="Нет открытых позиций")
        self.position_info_label.pack(fill=tk.X, pady=5, padx=5)
        
        # Кнопки для ручной торговли
        buttons_frame = ttk.Frame(position_frame)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        self.buy_btn = ttk.Button(buttons_frame, text="Купить", 
                                 command=lambda: self.manual_trade('buy'))
        self.buy_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.sell_btn = ttk.Button(buttons_frame, text="Продать", 
                                  command=lambda: self.manual_trade('sell'))
        self.sell_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.close_btn = ttk.Button(buttons_frame, text="Закрыть", 
                                   command=self.close_position)
        self.close_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    def create_settings_panel(self):
        """Создание панели с настройками"""
        settings_frame = ttk.LabelFrame(self.control_frame, text="Настройки")
        settings_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Настройки графика
        chart_settings_frame = ttk.Frame(settings_frame)
        chart_settings_frame.pack(fill=tk.X, pady=5)
        
        # Чекбоксы для отображения элементов графика
        self.show_volume_var = tk.BooleanVar(value=self.settings['chart']['show_volume'])
        show_volume_cb = ttk.Checkbutton(chart_settings_frame, text="Объем", 
                                       variable=self.show_volume_var,
                                       command=self.update_chart_settings)
        show_volume_cb.pack(anchor=tk.W, padx=5)
        
        self.show_orderbook_var = tk.BooleanVar(value=self.settings['chart']['show_orderbook'])
        show_orderbook_cb = ttk.Checkbutton(chart_settings_frame, text="Стакан заявок", 
                                          variable=self.show_orderbook_var,
                                          command=self.update_chart_settings)
        show_orderbook_cb.pack(anchor=tk.W, padx=5)
        
        self.show_density_var = tk.BooleanVar(value=self.settings['chart']['show_density_zones'])
        show_density_cb = ttk.Checkbutton(chart_settings_frame, text="Зоны плотности", 
                                        variable=self.show_density_var,
                                        command=self.update_chart_settings)
        show_density_cb.pack(anchor=tk.W, padx=5)
    
    def create_log_panel(self):
        """Создание панели с логами"""
        log_frame = ttk.LabelFrame(self.control_frame, text="Логи")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=5)
        
        # Текстовое поле для логов с прокруткой
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD, bg='#2a2a2a', fg='#e0e0e0')
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.tag_config('ERROR', foreground='#ff5555')
        self.log_text.tag_config('WARNING', foreground='#ffb86c')
        self.log_text.tag_config('SUCCESS', foreground='#50fa7b')
        self.log_text.tag_config('INFO', foreground='#8be9fd')
    
    def log_message(self, message, level="INFO"):
        """Логирование сообщения"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # Добавление в UI
        try:
            # Проверяем, что tkinter еще активен и виджет существует
            if hasattr(self, 'log_text') and hasattr(self.log_text, 'winfo_exists') and self.log_text.winfo_exists():
                self.log_text.insert(tk.END, log_entry, level)
                self.log_text.see(tk.END)
        except Exception as e:
            # Если произошла ошибка при вставке текста, просто логируем в консоль
            print(f"Ошибка вставки в лог: {e}")
        
        # Логирование через стандартный логгер
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "SUCCESS" or level == "INFO":
            logger.info(message)
    
    def update_position_display(self, position):
        """Обновление отображения информации о позиции"""
        if position is None:
            self.position_info_label.config(text="Нет открытых позиций")
            return
        
        position_type = "ЛОНГ" if position['type'] == 'buy' else "ШОРТ"
        entry_price = position['entry_price']
        size = position['size']
        pnl = position['pnl']
        pnl_percent = position['pnl_percent']
        
        position_text = f"{position_type} | Цена входа: {entry_price:.2f} | Размер: {size:.4f}\n"
        position_text += f"P&L: {pnl:.2f} ({pnl_percent:.2%})"
        
        self.position_info_label.config(text=position_text)
        
        # Обновление баланса
        self.balance_label.config(text=f"{self.trading_manager.balance:.2f}")
    
    def update_orders_display(self, orders):
        """Обновление отображения информации об ордерах"""
        # Реализация отображения ордеров в интерфейсе
        pass
    
    def update_chart_settings(self):
        """Обновление настроек графика"""
        # Обновление настроек в объекте settings
        self.settings['chart']['show_volume'] = self.show_volume_var.get()
        self.settings['chart']['show_orderbook'] = self.show_orderbook_var.get()
        self.settings['chart']['show_density_zones'] = self.show_density_var.get()
        
        # Сохранение настроек
        self.settings_manager.save_settings()
        
        # Обновление графика
        self.chart_manager.update_settings(self.settings['chart'])
        self.chart_manager.update_chart()
    
    def on_symbol_change(self, event=None):
        """Обработчик изменения символа"""
        new_symbol = self.symbol_var.get()
        if new_symbol != self.settings['trading']['symbol']:
            self.settings['trading']['symbol'] = new_symbol
            self.settings_manager.save_settings()
            
            # Обновление символа в модулях
            self.data_manager.set_symbol_interval(new_symbol, self.settings['trading']['interval'])
            self.trading_manager.symbol = new_symbol
            
            # Обновление данных
            self.update_data()
    
    def on_interval_change(self, event=None):
        """Обработчик изменения интервала"""
        new_interval = self.interval_var.get()
        if new_interval != self.settings['trading']['interval']:
            self.settings['trading']['interval'] = new_interval
            self.settings_manager.save_settings()
            
            # Обновление интервала в модулях
            self.data_manager.set_symbol_interval(self.settings['trading']['symbol'], new_interval)
            
            # Обновление данных
            self.update_data()
    
    def toggle_auto_trading(self):
        """Включение/выключение автоматической торговли"""
        auto_trading = self.auto_trading_var.get()
        self.settings['trading']['auto_trading'] = auto_trading
        self.settings_manager.save_settings()
        
        if auto_trading:
            self.log_message("Автоматическая торговля включена", "SUCCESS")
        else:
            self.log_message("Автоматическая торговля выключена", "INFO")
    
    def manual_trade(self, action):
        """Ручная торговля"""
        if self.data_manager.df is None or len(self.data_manager.df) == 0:
            self.log_message("Нет данных для торговли", "ERROR")
            return
        
        current_price = self.data_manager.df.iloc[-1]['close']
        self.trading_manager.process_signal(action, current_price)
    
    def close_position(self):
        """Закрытие текущей позиции"""
        if self.trading_manager.position is None:
            self.log_message("Нет открытых позиций", "WARNING")
            return
        
        if self.data_manager.df is None or len(self.data_manager.df) == 0:
            self.log_message("Нет данных для закрытия позиции", "ERROR")
            return
        
        current_price = self.data_manager.df.iloc[-1]['close']
        self.trading_manager.close_position(current_price)
    
    def update_ui_with_settings(self):
        """Обновление интерфейса в соответствии с настройками"""
        # Обновление контролов
        self.symbol_var.set(self.settings['trading']['symbol'])
        self.interval_var.set(self.settings['trading']['interval'])
        self.auto_trading_var.set(self.settings['trading']['auto_trading'])
        
        # Обновление настроек графика
        self.show_volume_var.set(self.settings['chart']['show_volume'])
        self.show_orderbook_var.set(self.settings['chart']['show_orderbook'])
        self.show_density_var.set(self.settings['chart']['show_density_zones'])
        
        # Обновление графика
        self.chart_manager.update_settings(self.settings['chart'])
        self.chart_manager.update_chart()
    
    def show_help(self):
        """Показать справку"""
        help_text = """
        🚀 Advanced Trading Bot v2.0 - AI Enhanced
        
        Горячие клавиши:
        F5 - Обновить данные
        F1 - Показать справку
        
        Основные функции:
        - Автоматическая торговля на основе ML-модели
        - Отображение графика с индикаторами
        - Отображение стакана заявок в реальном времени
        - Расчет зон плотности для определения уровней поддержки/сопротивления
        """
        
        messagebox.showinfo("Справка", help_text)
    
    def run(self):
        """Запуск приложения"""
        try:
            self.log_message("🚀 Торговый бот запущен!", "SUCCESS")
            self.log_message("📊 Инициализация модульной структуры...")
            self.log_message("🔗 Подключение к Binance API...")
            
            # Горячие клавиши
            self.root.bind('<F5>', lambda e: self.update_data())
            self.root.bind('<F1>', lambda e: self.show_help())
            
            # Запуск главного цикла
            self.root.mainloop()
            
        except KeyboardInterrupt:
            self.log_message("Получен сигнал прерывания", "ERROR")
        except Exception as e:
            self.log_message(f"Критическая ошибка: {e}", "ERROR")
        finally:
            # Остановка всех потоков и соединений
            self.data_manager.stop_websocket()
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
        import traceback
        print(f"Ошибка запуска: {e}")
        print("Подробная информация об ошибке:")
        traceback.print_exc()
        input("Нажмите Enter для выхода...")
