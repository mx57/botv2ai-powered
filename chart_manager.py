import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import time
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta

class ChartManager:
    """Модуль для управления графиками торгового бота"""
    
    def __init__(self, master, chart_frame, data_manager): # Added data_manager
        self.master = master
        self.chart_frame = chart_frame
        self.data_manager = data_manager # Store DataManager instance
        
        # Настройки графика
        self.fig = None
        self.canvas = None
        self.price_ax = None
        self.volume_ax = None
        
        # Данные для отображения
        self.df = None
        self.density_zones = []
        self.orderbook_data = {'bids': [], 'asks': []}
        
        # Кэширование для оптимизации
        self.cached_data = None
        self.cached_chart_data = None
        
        # Оптимизация производительности
        self.last_chart_update = 0
        self.chart_update_interval = 0.2  # Минимальный интервал между обновлениями (сек)
        
        # Навигация по графику
        self.zoom_level = 100
        self.offset = 0
        self.dragging = False
        self.last_x = 0 # Retained for now, though pan logic might change its use
        self.pan_start_x_screen = 0 
        self.pan_initial_offset = 0
        
        # Колбэки для событий
        self.on_error = None
        self.on_log = None
        
        # Настройки отображения
        self.settings = {
            'show_volume': True,
            'show_orderbook': True,
            'show_density_zones': True,
            'candle_width': 0.8,
            'orderbook_depth': 10,
            'chart_style': 'dark'
        }
    
    def apply_default_display_settings(self):
        """Применение настроек отображения по умолчанию"""
        # Настройки по умолчанию
        if not hasattr(self, 'chart_settings'):
            self.chart_settings = {
                'show_volumes': True,
                'show_density_zones': True,
                'show_orderbook': True,
                'show_indicators': True,
                'indicators': {
                    'show_sma': True,
                    'show_ema': True,
                    'show_bb': True,
                    'show_rsi': True,
                    'show_macd': True,
                    'show_legend': True,
                    'sma_periods': [10, 20, 50],
                    'ema_periods': [12, 26],
                    'bb_period': 20,
                    'bb_std': 2,
                    'rsi_period': 14,
                    'macd_fast': 12,
                    'macd_slow': 26,
                    'macd_signal': 9
                },
                'background_color': '#121212',
                'grid_alpha': 0.2,
                'chart_type': 'candlestick',  # Default chart type
                'show_intracandle_profile': False # Setting for volume profile
            }
    
    def setup_chart(self):
        """Инициализация графика"""
        # Применение настроек по умолчанию, если они не установлены
        if not hasattr(self, 'chart_settings'):
            self.apply_default_display_settings()
            
        # Проверка и очистка предыдущего графика, если он существует
        if hasattr(self, 'canvas') and self.canvas is not None:
            try:
                self.canvas.get_tk_widget().destroy()
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Ошибка при удалении предыдущего холста: {e}")
        
        if hasattr(self, 'fig') and self.fig is not None:
            try:
                plt.close(self.fig)
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Ошибка при закрытии предыдущей фигуры: {e}")
        
        # Создание фигуры и холста
        try:
            self.fig = Figure(figsize=(10, 6), dpi=100)
            if self.fig is None:
                if self.on_error:
                    self.on_error("Ошибка создания фигуры графика")
                return
                
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
            if self.canvas is None:
                if self.on_error:
                    self.on_error("Ошибка создания холста графика")
                return
                
            self.canvas.get_tk_widget().pack(side='top', fill='both', expand=True)
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка инициализации графика: {e}")
            return
        
        # Определение количества подграфиков в зависимости от настроек
        show_indicators = self.chart_settings.get('show_indicators', True)
        show_rsi = self.chart_settings.get('indicators', {}).get('show_rsi', True)
        show_macd = self.chart_settings.get('indicators', {}).get('show_macd', True)
        show_indicators = show_indicators and (show_rsi or show_macd)
        
        # Создание осей в зависимости от настроек
        if show_indicators:
            # График с индикаторами: цена, объем, индикаторы
            self.price_ax = self.fig.add_subplot(311)
            self.volume_ax = self.fig.add_subplot(312, sharex=self.price_ax)
            self.indicator_ax = self.fig.add_subplot(313, sharex=self.price_ax)
            self.fig.subplots_adjust(hspace=0.1, bottom=0.15)
        else:
            # График без индикаторов: только цена и объем
            self.price_ax = self.fig.add_subplot(211)  # Верхний график для цены
            self.volume_ax = self.fig.add_subplot(212, sharex=self.price_ax)  # Нижний график для объема
            self.fig.subplots_adjust(hspace=0.1)
            self.indicator_ax = None
        
        # Настройка внешнего вида
        self.setup_chart_style()
    
    def setup_chart_style(self):
        """Настройка стиля графика"""
        # Настройка цветов и стиля
        background_color = '#2d2d2d'  # Цвет фона по умолчанию
        grid_alpha = 0.3  # Прозрачность сетки по умолчанию
        
        # Применение настроек из chart_settings, если они есть
        if hasattr(self, 'chart_settings'):
            background_color = self.chart_settings.get('background_color', background_color)
            grid_alpha = self.chart_settings.get('grid_alpha', grid_alpha)
        
        # Применение цветов фона
        self.fig.patch.set_facecolor(background_color)
        self.price_ax.set_facecolor(background_color)
        self.volume_ax.set_facecolor(background_color)
        if hasattr(self, 'indicator_ax') and self.indicator_ax is not None:
            self.indicator_ax.set_facecolor(background_color)
        
        # Настройка сетки
        self.price_ax.grid(True, alpha=grid_alpha, linestyle='--', color='#555555')
        if hasattr(self, 'indicator_ax') and self.indicator_ax is not None:
            self.indicator_ax.grid(True, alpha=grid_alpha, linestyle='--', color='#555555')
        
        # Настройка меток
        self.price_ax.tick_params(axis='x', colors='#cccccc')
        self.price_ax.tick_params(axis='y', colors='#cccccc')
        self.volume_ax.tick_params(axis='y', colors='#cccccc')
        if hasattr(self, 'indicator_ax') and self.indicator_ax is not None:
            self.indicator_ax.tick_params(axis='both', colors='#cccccc')
        
        # Настройка подписей осей
        self.price_ax.set_ylabel('Price', color='#cccccc')
        
        # Форматирование дат на оси X
        self.price_ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n%d-%m'))
        
        # Удаление рамки
        for spine in self.price_ax.spines.values():
            spine.set_color('#555555')
        
        for spine in self.volume_ax.spines.values():
            spine.set_color('#555555')
            
        # Скрытие некоторых элементов для чистоты
        self.volume_ax.get_xaxis().set_visible(False)
        
    def update_settings(self, settings):
        """Обновление настроек графика"""
        try:
            # Проверка на изменение структуры графика (показ/скрытие индикаторов)
            structure_changed = False
            
            if hasattr(self, 'chart_settings'):
                # Проверка изменений в настройках индикаторов
                if 'show_indicators' in settings and 'show_indicators' in self.chart_settings:
                    if settings['show_indicators'] != self.chart_settings['show_indicators']:
                        structure_changed = True
                        
                # Проверка изменений в настройках объема
                if 'show_volume' in settings and 'show_volume' in self.chart_settings:
                    if settings['show_volume'] != self.chart_settings['show_volume']:
                        structure_changed = True
            else:
                # Если настройки еще не были установлены, считаем что структура изменилась
                structure_changed = True
            
            # Обновление настроек
            if not hasattr(self, 'chart_settings'):
                self.chart_settings = {}
                
            for key, value in settings.items():
                self.chart_settings[key] = value
            
            # Если структура графика изменилась, пересоздаем график
            if structure_changed:
                # Сохраняем текущие настройки масштабирования
                current_zoom = self.zoom_level if hasattr(self, 'zoom_level') else None
                current_offset = self.offset if hasattr(self, 'offset') else None
                
                # Пересоздаем график
                self.setup_chart()
                
                # Восстанавливаем настройки масштабирования
                if current_zoom is not None:
                    self.zoom_level = current_zoom
                if current_offset is not None:
                    self.offset = current_offset
            
            # Обновляем график с новыми настройками
            self.update_chart()
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обновления настроек графика: {e}")
    
    def on_key_press(self, event):
        """Обработка нажатия клавиш"""
        if self.df is None or len(self.df) == 0:
            return

        if event.key == 'left':
            # Сдвиг влево (старые данные)
            pan_amount = int(self.zoom_level * 0.1)  # Панорамирование на 10% от видимой области
            self.offset = min(len(self.df) - self.zoom_level, self.offset + pan_amount)
            self.update_chart()
        elif event.key == 'right':
            # Сдвиг вправо (новые данные)
            pan_amount = int(self.zoom_level * 0.1)  # Панорамирование на 10% от видимой области
            self.offset = max(0, self.offset - pan_amount)
            self.update_chart()
        elif event.key == 'up':
            # Увеличение масштаба (zoom in)
            old_zoom_level = self.zoom_level
            zoom_factor = 0.1  # Увеличение на 10%
            new_zoom_level = old_zoom_level * (1 - zoom_factor)
            new_zoom_level = int(max(10, min(new_zoom_level, len(self.df))))

            delta_zoom = new_zoom_level - old_zoom_level
            
            # Коррекция offset для центрирования зума
            self.offset -= delta_zoom / 2.0
            self.zoom_level = new_zoom_level
            self.offset = int(max(0, min(self.offset, len(self.df) - self.zoom_level)))
            self.update_chart()
        elif event.key == 'down':
            # Уменьшение масштаба (zoom out)
            old_zoom_level = self.zoom_level
            zoom_factor = 0.1  # Уменьшение на 10%
            new_zoom_level = old_zoom_level * (1 + zoom_factor)
            new_zoom_level = int(max(10, min(new_zoom_level, len(self.df))))

            delta_zoom = new_zoom_level - old_zoom_level

            # Коррекция offset для центрирования зума
            self.offset -= delta_zoom / 2.0
            self.zoom_level = new_zoom_level
            self.offset = int(max(0, min(self.offset, len(self.df) - self.zoom_level)))
            self.update_chart()
        elif event.key == 'r': # Reset view
            if self.df is not None and len(self.df) > 0:
                self.zoom_level = len(self.df) # Show all data
                self.offset = 0 # Align to the most recent data
                self.update_chart()
    
    def on_resize(self, event):
        """Обработка изменения размера окна"""
        # Обновление графика при изменении размера окна
        self.update_chart()
    
    def setup_event_handlers(self):
        """Настройка обработчиков событий для навигации по графику"""
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
    
    def on_scroll(self, event):
        """Обработка прокрутки для масштабирования с центром на курсоре мыши."""
        if event.inaxes != self.price_ax or self.df is None or len(self.df) == 0 or event.xdata is None:
            return

        # Получение текущей позиции курсора относительно оси X (в пикселях)
        x_cursor_pixel = event.x
        try:
            ax_bbox = self.price_ax.get_window_extent() # Получаем bbox в экранных координатах
            ax_x_abs_pixel = ax_bbox.x0
            ax_width_abs_pixel = ax_bbox.width
        except AttributeError:
             # Может возникнуть, если график еще не полностью отрисован
            return

        if ax_width_abs_pixel == 0: # Предотвращение деления на ноль
            return
            
        cursor_ratio = (x_cursor_pixel - ax_x_abs_pixel) / ax_width_abs_pixel
        cursor_ratio = max(0.0, min(1.0, cursor_ratio)) # Ограничение от 0 до 1

        old_zoom_level = float(self.zoom_level)
        zoom_factor = 0.1  # Масштабирование на 10%

        if event.button == 'up':  # Zoom In
            new_zoom_level = old_zoom_level * (1 - zoom_factor)
        else:  # Zoom Out
            new_zoom_level = old_zoom_level * (1 + zoom_factor)
        
        new_zoom_level = int(max(10, min(new_zoom_level, len(self.df))))

        if new_zoom_level == int(old_zoom_level): # Если масштаб не изменился значительно
            return

        delta_zoom = new_zoom_level - old_zoom_level
        
        # Коррекция offset для центрирования зума на курсоре
        # offset - количество точек справа от видимой области
        # Увеличение offset сдвигает график влево (показывает более старые данные)
        # Уменьшение offset сдвигает график вправо (показывает более новые данные)
        self.offset -= delta_zoom * (1 - cursor_ratio)
        
        self.zoom_level = new_zoom_level
        self.offset = int(max(0, min(self.offset, len(self.df) - self.zoom_level)))
        
        # Обновление графика
        self.master.after_idle(self.update_chart)
    
    def on_press(self, event):
        """Обработка нажатия кнопки мыши"""
        if event.inaxes != self.price_ax or event.x is None:
            return
        
        self.dragging = True
        self.pan_start_x_screen = event.x  # Store screen x-coordinate for panning
        self.pan_initial_offset = self.offset # Store initial offset for panning calculation
        # self.last_x = event.xdata # This was for data-coordinate based panning, may remove if not used elsewhere
    
    def on_release(self, event):
        """Обработка отпускания кнопки мыши"""
        self.dragging = False
    
    def on_motion(self, event):
        """Обработка перемещения мыши для панорамирования."""
        if not self.dragging or event.inaxes != self.price_ax or event.x is None or self.df is None or len(self.df) == 0:
            return
        
        try:
            ax_bbox = self.price_ax.get_window_extent()
            ax_width_pixels = ax_bbox.width
        except AttributeError:
             # Может возникнуть, если график еще не полностью отрисован
            return

        if ax_width_pixels == 0: # Предотвращение деления на ноль
            return

        current_x_screen = event.x
        # Delta in screen pixels from the start of the drag operation
        dx_screen = current_x_screen - self.pan_start_x_screen 
        
        # Calculate pan amount in data points
        # pan_ratio is the fraction of the axis width the mouse has been dragged
        pan_ratio = dx_screen / ax_width_pixels
        
        # data_pan_amount is how many data points this screen drag corresponds to
        data_pan_amount = int(pan_ratio * self.zoom_level)
        
        # A positive dx_screen (drag right) means the view should show newer data.
        # Newer data means a smaller offset (since offset is from the right end of the dataset).
        # So, new_offset = initial_offset - data_pan_amount
        new_offset = self.pan_initial_offset - data_pan_amount
        
        self.offset = int(max(0, min(new_offset, len(self.df) - self.zoom_level)))
        
        # Обновление графика
        self.master.after_idle(self.update_chart)
    
    def update_data(self, df, density_zones=None, orderbook_data=None):
        """Обновление данных для отображения"""
        self.df = df
        
        if density_zones is not None:
            self.density_zones = density_zones
        
        if orderbook_data is not None:
            self.orderbook_data = orderbook_data
        
        # Проверка на изменения данных
        if self.cached_data is not None:
            if (self.df.equals(self.cached_data['df']) and 
                self.density_zones == self.cached_data['zones'] and 
                self.orderbook_data == self.cached_data['orderbook']):
                return  # Данные не изменились
        
        # Кэширование новых данных
        self.cached_data = {
            'df': self.df.copy(),
            'zones': self.density_zones.copy() if isinstance(self.density_zones, list) else self.density_zones,
            'orderbook': self.orderbook_data.copy()
        }
        
        # Обновление графика
        self.master.after_idle(self.update_chart)
    
    def draw_chart(self):
        """Отрисовка графика с обработкой ошибок"""
        try:
            # Проверка наличия данных и необходимых компонентов графика
            if self.df is None or len(self.df) == 0:
                return
                
            if not hasattr(self, 'fig') or self.fig is None:
                self.setup_chart()
                if self.fig is None:
                    return
                    
            if not hasattr(self, 'canvas') or self.canvas is None:
                self.setup_chart()
                if self.canvas is None:
                    return
                    
            if not hasattr(self, 'price_ax') or self.price_ax is None or not hasattr(self, 'volume_ax') or self.volume_ax is None:
                self.setup_chart()
                if self.price_ax is None or self.volume_ax is None:
                    return
            
            # Применение настроек по умолчанию, если они не установлены
            if not hasattr(self, 'chart_settings'):
                self.apply_default_display_settings()
            
            # Ограничение данных для отображения
            start_idx = max(0, len(self.df) - self.zoom_level - self.offset)
            end_idx = min(len(self.df), len(self.df) - self.offset)
            
            if start_idx >= end_idx:
                return
            
            visible_df = self.df.iloc[start_idx:end_idx]
            
            # Отрисовка основного графика (свечи или линия)
            chart_type = self.chart_settings.get('chart_type', 'candlestick')
            if chart_type == 'candlestick':
                self.draw_candlesticks(visible_df)
            elif chart_type == 'line':
                self.draw_line_chart(visible_df)
            elif chart_type == 'ohlc': 
                self.draw_ohlc_chart(visible_df)
            elif chart_type == 'heikin_ashi': 
                self.draw_heikin_ashi_chart(visible_df)
            else: 
                self.draw_candlesticks(visible_df)

            # Отрисовка профиля объема внутри свечи, если включено
            if self.chart_settings.get('show_intracandle_profile', False) and not visible_df.empty:
                dates_num_vis = mdates.date2num(visible_df.index.to_pydatetime())
                candle_width_num = 0.01 
                if len(dates_num_vis) > 1:
                    candle_width_num = (dates_num_vis[1] - dates_num_vis[0]) * 0.8 
                elif len(dates_num_vis) == 1 and hasattr(self.df, 'index') and len(self.df.index) > 1: 
                    full_dates_num = mdates.date2num(self.df.index.to_pydatetime())
                    try: 
                        idx_in_full = self.df.index.get_loc(visible_df.index[0])
                        if idx_in_full > 0:
                            candle_width_num = (full_dates_num[idx_in_full] - full_dates_num[idx_in_full-1]) * 0.8
                        elif idx_in_full < len(full_dates_num) - 1:
                            candle_width_num = (full_dates_num[idx_in_full+1] - full_dates_num[idx_in_full]) * 0.8
                    except KeyError: 
                        pass 
                
                symbol = "BTCUSDT" 
                main_interval = "1h" 
                if hasattr(self.master, 'settings_manager') and self.master.settings_manager.settings:
                    trading_settings = self.master.settings_manager.settings.get('trading', {})
                    symbol = trading_settings.get('symbol', symbol)
                    main_interval = trading_settings.get('interval', main_interval)

                for i in range(len(visible_df)):
                    candle_row = visible_df.iloc[i]
                    candle_x_center_num = dates_num_vis[i]
                    main_candle_timestamp_ms = int(candle_row.name.timestamp() * 1000)
                    
                    # Use self.data_manager directly now
                    profile_data = self.data_manager.get_intra_candle_volume_profile(
                        symbol=symbol,
                        main_candle_timestamp=main_candle_timestamp_ms,
                        main_candle_interval=main_interval,
                        main_candle_high=candle_row['high'],
                        main_candle_low=candle_row['low']
                    )
                    if profile_data:
                        self._draw_single_candle_volume_profile(
                            self.price_ax, 
                            candle_x_center_num, 
                            candle_row, 
                            profile_data, 
                            candle_width_num
                        )

            # Отрисовка объема
            # Standardizing to 'show_volume' as it is used in the original part of this block and in SettingsManager.
            if self.chart_settings.get('show_volume', self.chart_settings.get('show_volumes', True)):
                self.draw_volumes(visible_df)
            
            # Отрисовка индикаторов
            if self.chart_settings.get('show_indicators', True):
                self.draw_indicators(visible_df)
            
            # Отрисовка зон плотности
            if self.density_zones and self.chart_settings.get('show_density_zones', True):
                self.draw_density_zones()
            
            # Отрисовка стакана заявок
            if self.orderbook_data and self.chart_settings.get('show_orderbook', True):
                self.draw_orderbook()
            
            # Настройка осей
            self.price_ax.set_xlim(visible_df.index[0], visible_df.index[-1])
            
            # Автоматическое масштабирование по Y
            price_margin = (visible_df['high'].max() - visible_df['low'].min()) * 0.1
            self.price_ax.set_ylim(visible_df['low'].min() - price_margin, 
                                   visible_df['high'].max() + price_margin)
            
            # Применение tight_layout для оптимального размещения элементов
            try:
                self.fig.tight_layout()
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Ошибка при применении tight_layout: {e}")
            
            # Отрисовка графика
            try:
                self.canvas.draw_idle()
            except Exception as e:
                if self.on_error:
                    self.on_error(f"Ошибка при отрисовке графика: {e}")
                # Если произошла ошибка при отрисовке, пробуем пересоздать график
                self.setup_chart()
                self.update_chart()
            
            # Обновление времени последнего обновления
            self.last_chart_update = time.time()
            
            # Кэширование данных для оптимизации
            self.cached_chart_data = {
                'key': (start_idx, end_idx, 
                       len(self.density_zones) if self.density_zones else 0, 
                       hash(str(self.orderbook_data)) if self.orderbook_data else 0,
                       hash(str(self.chart_settings)))
            }
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка при отрисовке графика: {e}")
            # В случае серьезной ошибки пробуем пересоздать график
            try:
                self.setup_chart()
            except Exception as setup_error:
                if self.on_error:
                    self.on_error(f"Не удалось пересоздать график: {setup_error}")
    
    def update_chart(self):
        """Обновление графика с оптимизацией производительности"""
        try:
            # Проверка на слишком частые обновления
            current_time = time.time()
            if (current_time - self.last_chart_update) < self.chart_update_interval:
                return
            
            # Проверка наличия данных и необходимых компонентов графика
            if self.df is None or len(self.df) == 0:
                return
            
            # Проверка, что фигура существует и доступна
            if not hasattr(self, 'fig') or self.fig is None:
                return
                
            # Проверка, что холст существует
            if not hasattr(self, 'canvas') or self.canvas is None:
                # Если холст не существует, пересоздаем его
                self.setup_chart()
                if self.canvas is None:  # Если не удалось создать холст
                    return
                
            # Проверка, что оси существуют
            if not hasattr(self, 'price_ax') or self.price_ax is None or not hasattr(self, 'volume_ax') or self.volume_ax is None:
                # Если оси не существуют, пересоздаем график
                self.setup_chart()
                if self.price_ax is None or self.volume_ax is None:  # Если не удалось создать оси
                    return
            
            # Применение настроек по умолчанию, если они не установлены
            if not hasattr(self, 'chart_settings'):
                self.apply_default_display_settings()
            
            # Ограничение данных для отображения
            start_idx = max(0, len(self.df) - self.zoom_level - self.offset)
            end_idx = min(len(self.df), len(self.df) - self.offset)
            
            if start_idx >= end_idx:
                return
            
            visible_df = self.df.iloc[start_idx:end_idx]
            
            # Проверка кэша для оптимизации
            cache_key = (start_idx, end_idx, 
                        len(self.density_zones) if self.density_zones else 0, 
                        hash(str(self.orderbook_data)) if self.orderbook_data else 0,
                        hash(str(self.chart_settings)))
            
            if self.cached_chart_data and self.cached_chart_data['key'] == cache_key:
                return  # Нет необходимости перерисовывать
            
            # Очистка графика
            self.price_ax.clear()
            self.volume_ax.clear()
            
            # Очистка осей индикаторов, если они есть
            if hasattr(self, 'indicator_ax') and self.indicator_ax is not None:
                self.indicator_ax.clear()
            
            # Применение стиля
            self.setup_chart_style()
            
            # Проверка, что фигура существует перед отрисовкой
            try:
                if self.fig is None or self.price_ax is None or self.volume_ax is None:
                    return
                    
                # Проверка, что фигура действительно существует
                fig = self.price_ax.get_figure()
                if fig is None:
                    return
            except Exception:
                # В случае ошибки при получении фигуры, выходим из метода
                return
                
            # Используем новый метод для отрисовки графика
            self.draw_chart()
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обновления графика: {e}")
    
    def draw_candlesticks(self, df):
        """Отрисовка свечей с оптимизацией производительности"""
        # Проверка, что фигура существует и инициализирована
        if not hasattr(self, 'fig') or self.fig is None or not hasattr(self, 'price_ax') or self.price_ax is None:
            return
            
        # Цвета для свечей
        up_color = '#26a69a'    # Зеленый для растущих свечей
        down_color = '#ef5350'  # Красный для падающих свечей
        
        # Создание массивов для векторизованной отрисовки
        dates = df.index
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        # Ширина свечи (в днях)
        if len(dates) > 1:
            width = 0.6 * (mdates.date2num(dates[1]) - mdates.date2num(dates[0]))
        else:
            width = 0.6 * 0.01  # Значение по умолчанию, если только одна дата
        
        # Создание массивов для растущих и падающих свечей
        up_indices = closes >= opens
        down_indices = closes < opens
        
        # Отрисовка теней (линии high-low)
        # Отрисовка теней свечей (вертикальные линии)
        # Заменяем vlines на индивидуальные линии, чтобы избежать использования LineCollection
        # self.price_ax.vlines(dates[up_indices], lows[up_indices], highs[up_indices], 
        #                    color=up_color, linewidth=1)
        # self.price_ax.vlines(dates[down_indices], lows[down_indices], highs[down_indices], 
        #                    color=down_color, linewidth=1)
        
        # Отрисовка теней свечей с использованием индивидуальных линий
        for i in range(len(dates)):
            if up_indices[i]:
                self.price_ax.plot([mdates.date2num(dates[i]), mdates.date2num(dates[i])], 
                                 [lows[i], highs[i]], 
                                 color=up_color, linewidth=1)
            else:
                self.price_ax.plot([mdates.date2num(dates[i]), mdates.date2num(dates[i])], 
                                 [lows[i], highs[i]], 
                                 color=down_color, linewidth=1)
        
        # Проверка, что фигура существует
        try:
            fig = self.price_ax.get_figure()
            if fig is None:
                # Если фигура не существует, просто выходим из метода
                return
        except Exception:
            # В случае ошибки при получении фигуры, выходим из метода
            return
        
        # Отрисовка тел свечей (прямоугольники)
        # Проверяем, что фигура существует и имеет атрибут dpi
        if fig is None or not hasattr(fig, 'dpi'):
            # Если фигура не существует или не имеет dpi, используем альтернативный метод отрисовки
            # Растущие свечи
            for i in range(len(dates)):
                if up_indices[i]:
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, opens[i]), 
                                  width, 
                                  closes[i] - opens[i],
                                  facecolor=up_color, 
                                  edgecolor=up_color, 
                                  linewidth=1)
                    self.price_ax.add_patch(rect)
                else:  # Падающие свечи
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, closes[i]), 
                                  width, 
                                  opens[i] - closes[i],
                                  facecolor=down_color, 
                                  edgecolor=down_color, 
                                  linewidth=1)
                    self.price_ax.add_patch(rect)
            return
        
        # Полностью отказываемся от PatchCollection, так как она вызывает ошибки с dpi
        # Вместо этого используем индивидуальные патчи для всех свечей
        try:
            # Растущие свечи
            for i in range(len(dates)):
                if up_indices[i]:
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, opens[i]), 
                                  width, 
                                  closes[i] - opens[i],
                                  facecolor=up_color, 
                                  edgecolor=up_color, 
                                  linewidth=1)
                    self.price_ax.add_patch(rect)
                else:  # Падающие свечи
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, closes[i]), 
                                  width, 
                                  opens[i] - closes[i],
                                  facecolor=down_color, 
                                  edgecolor=down_color, 
                                  linewidth=1)
                    self.price_ax.add_patch(rect)
        except Exception:
                    # Если не удалось установить размер, пропускаем
                    pass

    def draw_line_chart(self, df):
        """Отрисовка линейного графика (цена закрытия)"""
        if not hasattr(self, 'price_ax') or self.price_ax is None:
            return
        
        # Проверка наличия данных
        if df is None or df.empty or 'close' not in df.columns:
            if self.on_log:
                self.on_log("Данные для линейного графика отсутствуют или не содержат столбец 'close'", "WARNING")
            return

        try:
            self.price_ax.plot(df.index, df['close'], color='#4287f5', linewidth=1.2, label='Close Price')
            # Легенда будет обработана в draw_indicators, если включена
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка при отрисовке линейного графика: {e}")

    def _draw_single_candle_volume_profile(self, ax, candle_x_center_num, candle_data_row, profile_data, candle_width_num):
        """Отрисовка профиля объема для одной свечи."""
        if not profile_data:
            return

        max_profile_volume = max(p['total_volume'] for p in profile_data)
        if max_profile_volume == 0:
            return

        PROFILE_MAX_SCREEN_WIDTH_RATIO = 0.4  # Профиль занимает до 40% ширины основной свечи
        PROFILE_BAR_COLOR_TOTAL = '#8080D0'  # Синеватый для общего объема
        PROFILE_BAR_COLOR_BUY = '#60B060'   # Зеленоватый для объема покупок
        PROFILE_BAR_COLOR_SELL = '#D06060'  # Красноватый для объема продаж
        PROFILE_ALPHA = 0.65

        # Начальная X позиция для баров профиля (справа от свечи)
        profile_x_start = candle_x_center_num + candle_width_num * 0.55 # Небольшой отступ от свечи

        # Максимальная длина бара профиля в числовых координатах оси X
        max_bar_length_data_units = candle_width_num * PROFILE_MAX_SCREEN_WIDTH_RATIO
        
        # Определяем, есть ли данные о buy/sell объемах
        has_buy_sell_volume = all('buy_volume' in p and 'sell_volume' in p for p in profile_data)


        for bin_data in profile_data:
            price_start = bin_data['price_level_start']
            price_end = bin_data['price_level_end']
            total_volume = bin_data['total_volume']
            
            bar_y_position = (price_start + price_end) / 2
            bar_height_price_units = price_end - price_start
            
            if total_volume == 0 : continue # Пропускаем бины без объема

            # Длина бара пропорциональна объему
            bar_length_data_units = (total_volume / max_profile_volume) * max_bar_length_data_units

            if has_buy_sell_volume and total_volume > 0:
                buy_volume = bin_data.get('buy_volume', 0)
                sell_volume = bin_data.get('sell_volume', 0)

                buy_bar_length = (buy_volume / total_volume) * bar_length_data_units
                sell_bar_length = (sell_volume / total_volume) * bar_length_data_units
                
                # Рисуем объем продаж слева (или первым)
                if sell_volume > 0:
                    ax.barh(y=bar_y_position, width=sell_bar_length, height=bar_height_price_units,
                            left=profile_x_start, color=PROFILE_BAR_COLOR_SELL,
                            alpha=PROFILE_ALPHA, edgecolor=None, align='center')
                
                # Рисуем объем покупок справа (или вторым, поверх/рядом с продажами)
                if buy_volume > 0:
                    ax.barh(y=bar_y_position, width=buy_bar_length, height=bar_height_price_units,
                            left=profile_x_start + (sell_bar_length if sell_volume > 0 else 0) , color=PROFILE_BAR_COLOR_BUY,
                            alpha=PROFILE_ALPHA, edgecolor=None, align='center')
            else: # Рисуем только total_volume, если нет разделения
                 ax.barh(y=bar_y_position, width=bar_length_data_units, height=bar_height_price_units,
                        left=profile_x_start, color=PROFILE_BAR_COLOR_TOTAL,
                        alpha=PROFILE_ALPHA, edgecolor=None, align='center')


    def _calculate_heikin_ashi_df(self, df_orig):
        """Расчет данных для графика Heikin Ashi."""
        if df_orig is None or df_orig.empty:
            return pd.DataFrame()

        df = df_orig.copy()
        ha_df = pd.DataFrame(index=df.index)

        ha_df['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

        ha_df['HA_Open'] = np.nan
        if len(df) > 0:
            ha_df.loc[df.index[0], 'HA_Open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
            for i in range(1, len(df)):
                ha_df.loc[df.index[i], 'HA_Open'] = \
                    (ha_df['HA_Open'].iloc[i-1] + ha_df['HA_Close'].iloc[i-1]) / 2
        
        ha_df['HA_High'] = ha_df[['HA_Open', 'HA_Close']].join(df['high']).max(axis=1)
        ha_df['HA_Low'] = ha_df[['HA_Open', 'HA_Close']].join(df['low']).min(axis=1)
        
        # Для использования в методах отрисовки свечей, переименуем колонки в стандартные
        # но это лучше делать непосредственно перед вызовом draw_candlesticks_internal
        # или передавать имена колонок в тот метод. Пока оставим как есть.
        return ha_df

    def draw_heikin_ashi_chart(self, df):
        """Отрисовка графика Heikin Ashi."""
        if df is None or df.empty:
            return
        
        ha_df = self._calculate_heikin_ashi_df(df)
        if ha_df.empty:
            return

        # Используем существующий метод draw_candlesticks, но с данными Heikin Ashi
        # Для этого нужно временно подменить df['open'], df['high'], etc. или модифицировать draw_candlesticks
        # Проще создать копию DataFrame с нужными именами колонок
        # Цвета для Heikin Ashi свечей: зеленый если HA_Close > HA_Open, красный если HA_Close < HA_Open
        
        # Цвета для свечей
        up_color = '#26a69a'
        down_color = '#ef5350'

        dates_num = mdates.date2num(ha_df.index.to_pydatetime())

        # Ширина свечи
        if len(dates_num) > 1:
            width = 0.6 * (dates_num[1] - dates_num[0])
        else:
            # Если данных мало, используем значение по умолчанию, адаптированное под mdates
            # Это значение соответствует примерно 0.01 "дням" в числовом представлении mdates
            width = 0.6 * (0.01) 


        for i in range(len(ha_df)):
            ha_open = ha_df['HA_Open'].iloc[i]
            ha_close = ha_df['HA_Close'].iloc[i]
            ha_high = ha_df['HA_High'].iloc[i]
            ha_low = ha_df['HA_Low'].iloc[i]
            
            color = up_color if ha_close >= ha_open else down_color
            
            # Тени
            self.price_ax.plot([dates_num[i], dates_num[i]], [ha_low, ha_high], color=color, linewidth=1)
            
            # Тела
            body_bottom = min(ha_open, ha_close)
            body_height = abs(ha_open - ha_close)
            
            if body_height == 0: # Для Doji свечей, где Open == Close
                body_height = 0.01 * ha_close # Минимальная высота для видимости
                body_bottom = ha_close - body_height / 2


            rect = Rectangle((dates_num[i] - width/2, body_bottom), width, body_height,
                             facecolor=color, edgecolor=color, linewidth=1)
            self.price_ax.add_patch(rect)
            
    def draw_ohlc_chart(self, df):
        """Отрисовка графика OHLC."""
        if df is None or df.empty:
            return

        up_color = '#26a69a'
        down_color = '#ef5350'

        dates_num = mdates.date2num(df.index.to_pydatetime())
        
        # Ширина тиков для Open/Close
        # Адаптируем tick_width к масштабу оси X
        if len(dates_num) > 1:
            # tick_width как 10% от ширины одной "свечи"
            tick_width_data_units = 0.1 * (dates_num[1] - dates_num[0]) 
        else:
            # Если данных мало, используем небольшое фиксированное значение
            # Это значение должно быть достаточно малым, чтобы не перекрывать соседние элементы
            tick_width_data_units = 0.002 # Примерное значение для mdates

        for i in range(len(df)):
            o = df['open'].iloc[i]
            h = df['high'].iloc[i]
            l = df['low'].iloc[i]
            c = df['close'].iloc[i]
            
            color = up_color if c >= o else down_color
            
            # Вертикальная линия High-Low
            self.price_ax.plot([dates_num[i], dates_num[i]], [l, h], color=color, linewidth=1)
            
            # Тик Open (влево)
            self.price_ax.plot([dates_num[i] - tick_width_data_units, dates_num[i]], [o, o], color=color, linewidth=1)
            
            # Тик Close (вправо)
            self.price_ax.plot([dates_num[i], dates_num[i] + tick_width_data_units], [c, c], color=color, linewidth=1)

    def draw_volumes(self, df):
        """Отрисовка объемов с оптимизацией производительности"""
        # Цвета для объемов
        up_color = '#26a69a80'    # Зеленый с прозрачностью
        down_color = '#ef535080'  # Красный с прозрачностью
        
        # Проверка, что фигура существует
        try:
            fig = self.volume_ax.get_figure()
            if fig is None:
                # Если фигура не существует, просто выходим из метода
                return
        except Exception:
            # В случае ошибки при получении фигуры, выходим из метода
            return
        
        # Создание массивов для векторизованной отрисовки
        dates = df.index
        opens = df['open'].values
        closes = df['close'].values
        volumes = df['volume'].values
        
        # Ширина столбца объема
        if len(dates) > 1:
            width = 0.8 * (mdates.date2num(dates[1]) - mdates.date2num(dates[0]))
        else:
            width = 0.8 * 0.01  # Значение по умолчанию, если только одна дата
        
        # Создание массивов для растущих и падающих свечей
        up_indices = closes >= opens
        down_indices = closes < opens
        
        # Отрисовка объемов для растущих свечей
        if any(up_indices):
            self.volume_ax.bar([mdates.date2num(dates[i]) for i in range(len(dates)) if up_indices[i]], 
                             [volumes[i] for i in range(len(volumes)) if up_indices[i]], 
                             width=width, 
                             color=up_color, 
                             alpha=0.5)
        
        # Отрисовка объемов для падающих свечей
        if any(down_indices):
            self.volume_ax.bar([mdates.date2num(dates[i]) for i in range(len(dates)) if down_indices[i]], 
                             [volumes[i] for i in range(len(volumes)) if down_indices[i]], 
                             width=width, 
                             color=down_color, 
                             alpha=0.5)
        
        # Настройка оси объемов
        self.volume_ax.set_ylim(0, df['volume'].max() * 3)
        self.volume_ax.spines['right'].set_position(('axes', 1.02))
        self.volume_ax.set_ylabel('Volume', color='#666666')
    
    def draw_density_zones(self):
        """Отрисовка зон плотности"""
        if not self.density_zones:
            return
            
        # Проверка, что фигура существует
        try:
            fig = self.price_ax.get_figure()
            if fig is None:
                # Если фигура не существует, просто выходим из метода
                return
        except Exception:
            # В случае ошибки при получении фигуры, выходим из метода
            return
        
        # Получение границ графика
        x_min, x_max = self.price_ax.get_xlim()
        
        # Создаем список прямоугольников для всех зон
        rectangles = []
        
        for zone in self.density_zones:
            center = zone['center']
            width = zone['width']
            zone_type = zone['type']
            strength = zone['strength']
            
            # Цвет зоны в зависимости от типа
            color = '#26a69a40' if zone_type == 'support' else '#ef535040'  # С прозрачностью
            edge_color = '#26a69a' if zone_type == 'support' else '#ef5350'
            
            # Создание прямоугольника для зоны
            rect = Rectangle((x_min, center - width/2), 
                           x_max - x_min, 
                           width, 
                           facecolor=color, 
                           edgecolor=edge_color, 
                           linewidth=1, 
                           alpha=min(0.8, strength * 2))
            
            rectangles.append(rect)
        
        # Добавляем все прямоугольники по отдельности, избегая использования PatchCollection
        if rectangles:
            try:
                # Добавляем патчи по отдельности, чтобы избежать проблем с dpi
                for rect in rectangles:
                    self.price_ax.add_patch(rect)
            except Exception:
                # Игнорируем ошибки при добавлении патчей
                pass
    
    def draw_orderbook(self):
        """Отрисовка стакана заявок"""
        if not self.orderbook_data or not self.orderbook_data['bids'] or not self.orderbook_data['asks']:
            return
            
        # Проверка, что фигура существует
        try:
            fig = self.price_ax.get_figure()
            if fig is None:
                # Если фигура не существует, просто выходим из метода
                return
        except Exception:
            # В случае ошибки при получении фигуры, выходим из метода
            return
        
        # Получение границ графика
        y_min, y_max = self.price_ax.get_ylim()
        x_max = self.price_ax.get_xlim()[1]
        
        # Преобразование данных стакана
        bids = np.array(self.orderbook_data['bids'], dtype=float)
        asks = np.array(self.orderbook_data['asks'], dtype=float)
        
        # Нормализация объемов
        max_volume = max(np.max(bids[:, 1]) if len(bids) > 0 else 0, 
                        np.max(asks[:, 1]) if len(asks) > 0 else 0)
        
        if max_volume == 0:
            return
        
        # Ширина графика для стакана (10% от ширины)
        width = (y_max - y_min) * 0.1
        
        # Создаем списки прямоугольников для ордеров
        bid_rectangles = []
        ask_rectangles = []
        
        # Подготовка ордеров на покупку (bids)
        if len(bids) > 0:
            bid_volumes = bids[:, 1] / max_volume * width
            bid_prices = bids[:, 0]
            
            for i in range(len(bids)):
                rect = Rectangle((x_max - bid_volumes[i], bid_prices[i] - 0.5), 
                               bid_volumes[i], 
                               1, 
                               facecolor='#26a69a40', 
                               edgecolor='#26a69a', 
                               linewidth=0.5, 
                               alpha=0.5)
                bid_rectangles.append(rect)
        
        # Подготовка ордеров на продажу (asks)
        if len(asks) > 0:
            ask_volumes = asks[:, 1] / max_volume * width
            ask_prices = asks[:, 0]
            
            for i in range(len(asks)):
                rect = Rectangle((x_max - ask_volumes[i], ask_prices[i] - 0.5), 
                               ask_volumes[i], 
                               1, 
                               facecolor='#ef535040', 
                               edgecolor='#ef5350', 
                               linewidth=0.5, 
                               alpha=0.5)
                ask_rectangles.append(rect)
        
        # Добавляем все прямоугольники по отдельности, избегая использования PatchCollection
        try:
            # Добавляем ордера на покупку по отдельности
            for rect in bid_rectangles:
                self.price_ax.add_patch(rect)
            
            # Добавляем ордера на продажу по отдельности
            for rect in ask_rectangles:
                self.price_ax.add_patch(rect)
        except Exception:
            # Игнорируем ошибки при добавлении патчей
             pass
             
    def update_orderbook(self, orderbook_data):
        """Обновление данных стакана заявок"""
        try:
            self.orderbook_data = orderbook_data
            
            # Если включено отображение стакана, обновляем график
            if hasattr(self, 'settings') and self.settings.get('show_orderbook', False):
                self.update_chart()
        except Exception as e:
            if self.on_error:
                self.on_error(f"Ошибка обновления стакана: {e}")
    
    def draw_indicators(self, df):
        """Отрисовка технических индикаторов"""
        if not hasattr(self, 'chart_settings') or not self.chart_settings.get('show_indicators', True):
            return
        
        # Проверка наличия данных
        if df is None or len(df) < 20:
            return
            
        # Проверка, что фигура существует
        try:
            fig = self.price_ax.get_figure()
            if fig is None:
                # Если фигура не существует, просто выходим из метода
                return
        except Exception:
            # В случае ошибки при получении фигуры, выходим из метода
            return
        
        # Получение настроек индикаторов
        indicators = self.chart_settings.get('indicators', {})
        
        # Отрисовка SMA
        if indicators.get('show_sma', True):
            sma_periods = indicators.get('sma_periods', [10, 20, 50])
            colors = ['#f5d442', '#42f5a7', '#4287f5']
            
            for i, period in enumerate(sma_periods):
                if len(df) > period:
                    sma = df['close'].rolling(window=period).mean()
                    self.price_ax.plot(df.index, sma, color=colors[i % len(colors)], 
                                     linewidth=1.2, alpha=0.8, label=f'SMA {period}')
        
        # Отрисовка EMA
        if indicators.get('show_ema', True):
            ema_periods = indicators.get('ema_periods', [12, 26])
            colors = ['#f542f2', '#f54242']
            
            for i, period in enumerate(ema_periods):
                if len(df) > period:
                    ema = df['close'].ewm(span=period, adjust=False).mean()
                    self.price_ax.plot(df.index, ema, color=colors[i % len(colors)], 
                                     linewidth=1.2, alpha=0.8, label=f'EMA {period}')
        
        # Отрисовка Bollinger Bands
        if indicators.get('show_bb', True):
            bb_period = indicators.get('bb_period', 20)
            bb_std = indicators.get('bb_std', 2)
            
            if len(df) > bb_period:
                sma = df['close'].rolling(window=bb_period).mean()
                std = df['close'].rolling(window=bb_period).std()
                upper_band = sma + (std * bb_std)
                lower_band = sma - (std * bb_std)
                
                self.price_ax.plot(df.index, upper_band, color='#a142f5', linewidth=1, alpha=0.6, label=f'BB Upper')
                self.price_ax.plot(df.index, lower_band, color='#a142f5', linewidth=1, alpha=0.6, label=f'BB Lower')
                
                # Заменяем fill_between на индивидуальные прямоугольники для избежания проблем с dpi
                # self.price_ax.fill_between(df.index, upper_band, lower_band, color='#a142f530')
                
                # Проверка, что фигура существует
                try:
                    fig = self.price_ax.get_figure()
                    if fig is None:
                        # Если фигура не существует, просто выходим из метода
                        return
                except Exception:
                    # В случае ошибки при получении фигуры, выходим из метода
                    return
        
        # Проверка наличия оси для индикаторов
        if not hasattr(self, 'indicator_ax') or self.indicator_ax is None:
            return
            
        # Отрисовка RSI
        if indicators.get('show_rsi', True):
            rsi_period = indicators.get('rsi_period', 14)
            
            if len(df) > rsi_period + 1:
                # Расчет RSI
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
                loss = -delta.where(delta < 0, 0).rolling(window=rsi_period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                
                # Отрисовка RSI
                self.indicator_ax.plot(df.index, rsi, color='#f54263', linewidth=1, alpha=0.8, label='RSI')
                self.indicator_ax.axhline(y=70, color='#f54242', linestyle='--', alpha=0.5)
                self.indicator_ax.axhline(y=30, color='#42f54e', linestyle='--', alpha=0.5)
                self.indicator_ax.set_ylim(0, 100)
                self.indicator_ax.set_ylabel('RSI', color='#f54263')
        
        # Отрисовка MACD
        if indicators.get('show_macd', True):
            macd_fast = indicators.get('macd_fast', 12)
            macd_slow = indicators.get('macd_slow', 26)
            macd_signal = indicators.get('macd_signal', 9)
            
            if len(df) > macd_slow + macd_signal:
                # Расчет MACD
                ema_fast = df['close'].ewm(span=macd_fast, adjust=False).mean()
                ema_slow = df['close'].ewm(span=macd_slow, adjust=False).mean()
                macd_line = ema_fast - ema_slow
                signal_line = macd_line.ewm(span=macd_signal, adjust=False).mean()
                histogram = macd_line - signal_line
                
                # Отрисовка MACD
                if not indicators.get('show_rsi', True):  # Если RSI не отображается, используем всю ось для MACD
                    self.indicator_ax.plot(df.index, macd_line, color='#4287f5', linewidth=1, alpha=0.8, label='MACD')
                    self.indicator_ax.plot(df.index, signal_line, color='#f5a742', linewidth=1, alpha=0.8, label='Signal')
                    
                    # Отрисовка гистограммы
                    for i in range(len(df)):
                        if i < len(histogram):
                            color = '#42f54e' if histogram.iloc[i] > 0 else '#f54242'
                            self.indicator_ax.bar(df.index[i], histogram.iloc[i], width=0.7, color=color, alpha=0.5)
                    
                    self.indicator_ax.set_ylabel('MACD', color='#4287f5')
                else:  # Если RSI отображается, делим ось для MACD и RSI
                    # Создаем вторую ось Y для MACD
                    macd_ax = self.indicator_ax.twinx()
                    macd_ax.plot(df.index, macd_line, color='#4287f5', linewidth=1, alpha=0.8, label='MACD')
                    macd_ax.plot(df.index, signal_line, color='#f5a742', linewidth=1, alpha=0.8, label='Signal')
                    
                    # Отрисовка гистограммы
                    for i in range(len(df)):
                        if i < len(histogram):
                            color = '#42f54e' if histogram.iloc[i] > 0 else '#f54242'
                            macd_ax.bar(df.index[i], histogram.iloc[i], width=0.7, color=color, alpha=0.5)
                    
                    macd_ax.set_ylabel('MACD', color='#4287f5')
                    macd_ax.tick_params(axis='y', colors='#4287f5')
        
        # Добавление легенды
        if indicators.get('show_legend', True):
            self.price_ax.legend(loc='upper left', fontsize=8)