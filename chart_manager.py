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
    
    def __init__(self, master, chart_frame):
        self.master = master
        self.chart_frame = chart_frame
        
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

        # Атрибуты для хранения художников Matplotlib
        self.candlestick_lines = None
        self.candlestick_bodies = []
        self.volume_bars = []
        self.density_zone_rects = []
        self.orderbook_bid_rects = []
        self.orderbook_ask_rects = []

        self.last_style_settings_hash = None # Для отслеживания изменений стиля
        
        # Оптимизация производительности
        self.last_chart_update = 0
        self.chart_update_interval = 0.2  # Минимальный интервал между обновлениями (сек)
        
        # Навигация по графику
        self.zoom_level = 100
        self.offset = 0
        self.dragging = False
        self.last_x = 0
        
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
                'grid_alpha': 0.2
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

        # Инициализация или очистка коллекций художников
        self._initialize_artists()
    
    def _initialize_artists(self):
        """Инициализирует или очищает списки художников."""
        self.candlestick_lines = None # Будет LineCollection
        self.candlestick_bodies = []
        self.volume_bars = []
        self.density_zone_rects = []
        self.orderbook_bid_rects = []
        self.orderbook_ask_rects = []

        # Удаление существующих художников с осей, если они есть
        # Это важно, если setup_chart вызывается повторно (например, при смене темы)
        if hasattr(self, 'price_ax') and self.price_ax:
            # Удаляем старые коллекции и патчи, чтобы избежать дублирования
            if self.candlestick_lines:
                try: self.candlestick_lines.remove()
                except Exception: pass # Игнорируем, если уже удален или не добавлен
            for collection_list in [self.candlestick_bodies, self.density_zone_rects, self.orderbook_bid_rects, self.orderbook_ask_rects]:
                for item in collection_list:
                    try: item.remove()
                    except Exception: pass

        if hasattr(self, 'volume_ax') and self.volume_ax:
            for item in self.volume_bars:
                try: item.remove()
                except Exception: pass

        # Сбрасываем last_style_settings_hash, чтобы стиль применился принудительно
        self.last_style_settings_hash = None


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
        if event.key == 'left':
            # Сдвиг влево
            self.offset = min(len(self.df) - self.zoom_level, self.offset + 10)
            self.update_chart()
        elif event.key == 'right':
            # Сдвиг вправо
            self.offset = max(0, self.offset - 10)
            self.update_chart()
        elif event.key == 'up':
            # Увеличение масштаба
            self.zoom_level = max(10, self.zoom_level - 10)
            self.update_chart()
        elif event.key == 'down':
            # Уменьшение масштаба
            self.zoom_level = min(500, self.zoom_level + 10)
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
        """Обработка прокрутки для масштабирования"""
        if event.inaxes != self.price_ax:
            return
        
        # Изменение уровня масштабирования
        if event.button == 'up':
            self.zoom_level = max(10, self.zoom_level - 5)
        else:
            self.zoom_level = min(500, self.zoom_level + 5)
        
        # Обновление графика
        self.master.after_idle(self.update_chart)
    
    def on_press(self, event):
        """Обработка нажатия кнопки мыши"""
        if event.inaxes != self.price_ax:
            return
        
        self.dragging = True
        self.last_x = event.xdata
    
    def on_release(self, event):
        """Обработка отпускания кнопки мыши"""
        self.dragging = False
    
    def on_motion(self, event):
        """Обработка перемещения мыши"""
        if not self.dragging or event.inaxes != self.price_ax or event.xdata is None:
            return
        
        # Расчет смещения
        dx = event.xdata - self.last_x
        self.offset += int(dx * 5)
        self.offset = max(0, min(self.offset, len(self.df) - self.zoom_level))
        self.last_x = event.xdata
        
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
            
            # Отрисовка свечей
            self.draw_candlesticks(visible_df)
            
            # Отрисовка объема
            if self.chart_settings.get('show_volume', True):
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
                # TODO: Potentially still need to redraw if zoom/pan changed,
                # even if underlying data is the same. For now, assume this check is sufficient.
                return  # Нет необходимости перерисовывать
            
            # Очистка старых художников вместо полной очистки осей
            for p in self.candlestick_bodies + self.volume_bars + self.density_zone_rects + self.orderbook_bid_rects + self.orderbook_ask_rects:
                if p.axes: # Проверяем, что патч все еще на осях
                    p.remove()
            self.candlestick_bodies.clear()
            self.volume_bars.clear()
            self.density_zone_rects.clear()
            self.orderbook_bid_rects.clear()
            self.orderbook_ask_rects.clear()

            if self.candlestick_lines:
                if self.candlestick_lines.axes: # Проверяем, что коллекция все еще на осях
                    self.candlestick_lines.remove()
                self.candlestick_lines = None # Пересоздадим в draw_candlesticks
            
            # Очистка индикаторов (они обычно рисуются как линии, которые могут меняться)
            if hasattr(self, 'indicator_ax') and self.indicator_ax is not None:
                self.indicator_ax.clear() # Пока оставляем полную очистку для индикаторов
                # TODO: Оптимизировать отрисовку индикаторов аналогично свечам/объемам

            # Применение стиля (возможно, не на каждом обновлении)
            current_style_settings = {
                'background_color': self.chart_settings.get('background_color'),
                'grid_alpha': self.chart_settings.get('grid_alpha'),
                # Добавьте другие настройки стиля, если они влияют на setup_chart_style
            }
            current_style_hash = hash(str(current_style_settings))

            if current_style_hash != self.last_style_settings_hash:
                self.setup_chart_style() # Применяем стиль только если он изменился
                self.last_style_settings_hash = current_style_hash
            else:
                # Важно: если стиль не менялся, нужно убедиться, что основные элементы стиля осей
                # (например, цвет фона) не были сброшены индикаторной очисткой.
                # self.price_ax.set_facecolor(...) и т.д. могут быть нужны здесь, если clear() их сбрасывает.
                # Однако, индикаторы рисуются на indicator_ax, price_ax и volume_ax не должны страдать.
                pass
            
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
        
        # Отрисовка теней (фитилей) с использованием LineCollection
        lines_data = []
        line_colors_data = []
        for i in range(len(dates)):
            lines_data.append([(mdates.date2num(dates[i]), lows[i]), (mdates.date2num(dates[i]), highs[i])])
            if up_indices[i]:
                line_colors_data.append(up_color)
            else:
                line_colors_data.append(down_color)

        if self.candlestick_lines is None: # Создаем, если еще не существует
            self.candlestick_lines = LineCollection(lines_data, colors=line_colors_data, linewidths=1)
            self.price_ax.add_collection(self.candlestick_lines)
        else: # Обновляем существующую
            self.candlestick_lines.set_segments(lines_data)
            self.candlestick_lines.set_colors(line_colors_data)
            if not self.candlestick_lines.axes: # Если коллекция была удалена, добавляем снова
                 self.price_ax.add_collection(self.candlestick_lines)


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
        # Вместо этого используем индивидуальные патчи для всех свечей.
        # self.candlestick_bodies уже очищен в update_chart()
        try:
            new_bodies = []
            for i in range(len(dates)):
                if up_indices[i]:
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, opens[i]), 
                                  width, 
                                  closes[i] - opens[i],
                                  facecolor=up_color, 
                                  edgecolor=up_color, 
                                  linewidth=1)
                else:  # Падающие свечи
                    rect = Rectangle((mdates.date2num(dates[i]) - width/2, closes[i]), 
                                  width, 
                                  opens[i] - closes[i],
                                  facecolor=down_color, 
                                  edgecolor=down_color, 
                                  linewidth=1)
                self.price_ax.add_patch(rect) # Добавляем сразу на оси
                new_bodies.append(rect)
            self.candlestick_bodies = new_bodies # Сохраняем список новых патчей
        except Exception as e:
            if self.on_error: self.on_error(f"Ошибка отрисовки тел свечей: {e}")
            # Если не удалось установить размер, пропускаем
            pass
    
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

        # self.volume_bars уже очищен в update_chart()
        new_volume_bars = []
        for i in range(len(dates)):
            color = up_color if up_indices[i] else down_color
            rect = Rectangle((mdates.date2num(dates[i]) - width/2, 0),
                           width,
                           volumes[i],
                           facecolor=color, # alpha уже в цвете
                           edgecolor=color)
            self.volume_ax.add_patch(rect)
            new_volume_bars.append(rect)
        self.volume_bars = new_volume_bars
        
        # Настройка оси объемов
        if not df['volume'].empty and df['volume'].max() > 0:
            self.volume_ax.set_ylim(0, df['volume'].max() * 3)
        else:
            self.volume_ax.set_ylim(0, 1) # Запасной вариант для оси Y, если нет объемов
        self.volume_ax.spines['right'].set_position(('axes', 1.02)) # Это может вызывать проблемы, если volume_ax не основной
        self.volume_ax.set_ylabel('Volume', color='#cccccc') # Цвет как у других меток
        # Убедимся, что ось X для объемов синхронизирована с ценовой осью
        self.volume_ax.set_xlim(self.price_ax.get_xlim())
    
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
        # self.density_zone_rects уже очищен в update_chart()
        
        new_density_zones_rects = []
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
                           alpha=min(0.8, strength * 2)) # Убедимся, что strength корректно влияет на alpha
            
            self.price_ax.add_patch(rect)
            new_density_zones_rects.append(rect)
        self.density_zone_rects = new_density_zones_rects
        
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
        # self.orderbook_bid_rects и self.orderbook_ask_rects уже очищены в update_chart()

        new_bid_rects = []
        new_ask_rects = []
        
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
                               linewidth=0.5) # alpha уже в цвете
                self.price_ax.add_patch(rect)
                new_bid_rects.append(rect)
            self.orderbook_bid_rects = new_bid_rects
        
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
                               linewidth=0.5) # alpha уже в цвете
                self.price_ax.add_patch(rect)
                new_ask_rects.append(rect)
            self.orderbook_ask_rects = new_ask_rects
             
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