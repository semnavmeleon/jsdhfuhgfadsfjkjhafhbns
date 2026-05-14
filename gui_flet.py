import flet as ft
import subprocess
import struct
import threading
import os
import json
from datetime import timedelta
from core_logic import TrackInfo, ModificationWorker

CONFIG_FILE = "vk_modifier_config.json"

SUPPORTED_FORMATS = {
    'mp3': 'MP3 (lossy)',
    'flac': 'FLAC (lossless)',
    'wav': 'WAV (lossless)',
    'ogg': 'OGG Vorbis (lossy)',
    'aac': 'AAC (lossy)',
    'm4a': 'M4A AAC (lossy)',
}

FORMAT_CODECS = {
    'mp3': 'libmp3lame',
    'flac': 'flac',
    'wav': 'pcm_s16le',
    'ogg': 'libvorbis',
    'aac': 'aac',
    'm4a': 'aac',
}

QUALITY_PRESETS = {
    'mp3': ['320 kbps (CBR)', '256 kbps (CBR)', '192 kbps (CBR)', '128 kbps (CBR)', 'VBR Высшее (Q0)'],
    'aac': ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
    'm4a': ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
    'ogg': ['Качество 10 (макс)', 'Качество 8 (высокое)', 'Качество 6 (среднее)'],
}


class WaveformCanvas(ft.Column):
    """Виджет для отрисовки waveform с использованием PIL"""
    
    def __init__(self, title="Waveform", color="#5599ff", bg_color="#0d1117"):
        super().__init__()
        self.title = title
        self.color = color
        self.bg_color = bg_color
        self.samples = []
        self.zoom = 1.0
        self.offset = 0.0
        self._img_base64 = ""
        
        # Создаем изображение для waveform
        self.wave_image = ft.Image(
            src="",
            fit=ft.ImageFit.FILL,
            height=250,
        )
        
        self.wave_title = ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=color)
        
        self.controls = [
            self.wave_title,
            ft.Container(
                height=250,
                bgcolor=bg_color,
                border_radius=8,
                content=self.wave_image,
            ),
            ft.Row([
                ft.IconButton(icon=ft.icons.ZOOM_OUT, icon_size=20, on_click=self._on_zoom_out),
                ft.Text("Zoom: 1.0x", size=12),
                ft.IconButton(icon=ft.icons.ZOOM_IN, icon_size=20, on_click=self._on_zoom_in),
            ], alignment=ft.MainAxisAlignment.CENTER),
        ]
    
    def set_samples(self, samples):
        """Устанавливает сэмплы и перерисовывает waveform"""
        self.samples = samples
        self.offset = 0.0
        self.zoom = 1.0
        self._redraw()
    
    def _redraw(self):
        """Перерисовка waveform"""
        if not hasattr(self, 'wave_image'):
            return
            
        try:
            from PIL import Image, ImageDraw
            width, height = 800, 250
            
            img = Image.new('RGB', (width, height), self.bg_color.lstrip('#'))
            draw = ImageDraw.Draw(img)
            
            mid = height // 2
            draw_h = mid - 10
            
            # Рисуем центральную линию
            draw.line([(0, mid), (width, mid)], fill="#2a2a2a", width=1)
            
            if self.samples:
                # Применяем zoom и offset
                n = len(self.samples)
                visible_samples = int(n / max(1.0, self.zoom))
                start_idx = int(self.offset * max(0, n - visible_samples)) if n > visible_samples else 0
                end_idx = min(start_idx + visible_samples, n)
                
                if end_idx <= start_idx:
                    start_idx = 0
                    end_idx = n
                
                view_samples = self.samples[start_idx:end_idx]
                
                if view_samples:
                    # Парсим цвет
                    r = int(self.color[1:3], 16)
                    g = int(self.color[3:5], 16)
                    b = int(self.color[5:7], 16)
                    inner_r = int(r * 0.55)
                    inner_g = int(g * 0.55)
                    inner_b = int(b * 0.55)
                    inner_color = f'#{inner_r:02x}{inner_g:02x}{inner_b:02x}'
                    
                    # Рисуем waveform
                    for x in range(width):
                        i0 = int(x * len(view_samples) / width)
                        i1 = int((x + 1) * len(view_samples) / width)
                        if i1 <= i0:
                            i1 = i0 + 1
                        chunk = view_samples[i0:min(i1, len(view_samples))]
                        if not chunk:
                            continue
                        
                        peak_pos = max(chunk)
                        peak_neg = min(chunk)
                        rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
                        
                        peak_pos = max(0.0, min(1.0, peak_pos))
                        peak_neg = min(0.0, max(-1.0, peak_neg))
                        rms = min(1.0, rms)
                        
                        y_top = mid - int(peak_pos * draw_h)
                        y_bot = mid - int(peak_neg * draw_h)
                        y_rms_top = mid - int(rms * draw_h)
                        y_rms_bot = mid + int(rms * draw_h)
                        
                        if y_top >= y_bot:
                            y_bot = y_top + 1
                        
                        # RMS (внутренняя часть)
                        draw.line([(x, y_rms_top), (x, y_rms_bot)], fill=self.color.lstrip('#'), width=1)
                        # Peak (внешняя часть)
                        draw.line([(x, y_top), (x, y_bot)], fill=inner_color.lstrip('#'), width=1)
            
            # Сохраняем изображение
            import io
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            import base64
            data = base64.b64encode(buf.getvalue()).decode()
            
            # Обновляем изображение
            self.wave_image.src = f"data:image/png;base64,{data}"
                
        except Exception as e:
            print(f"Error drawing waveform: {e}")
    
    def _on_zoom_in(self, e):
        self.zoom = min(10.0, self.zoom * 1.5)
        self._redraw()
    
    def _on_zoom_out(self, e):
        self.zoom = max(1.0, self.zoom / 1.5)
        self.offset = 0.0
        self._redraw()


def main(page: ft.Page):
    page.title = "VK Modifier (Flet)"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    
    # Состояние приложения
    state = {
        'input_files': [],
        'tracks_info': [],
        'current_index': -1,
        'output_dir': os.path.expanduser("~/Desktop/Output"),
        'waveform_samples': None,
        'ffmpeg_ok': False,
    }
    
    # Проверка ffmpeg
    def check_ffmpeg():
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    state['ffmpeg_ok'] = check_ffmpeg()
    
    # Элементы управления параметрами
    v_pitch = ft.Checkbox(label="Pitch Shift", value=False)
    v_pitch_val = ft.Slider(min=-12, max=12, divisions=24, value=0.5, label="{value}")
    
    v_speed = ft.Checkbox(label="Speed Change", value=False)
    v_speed_val = ft.Slider(min=0.5, max=2.0, divisions=15, value=1.0, label="{value}")
    
    v_eq = ft.Checkbox(label="EQ", value=False)
    v_eq_type = ft.Dropdown(
        options=[
            ft.dropdown.Option("0", "Low Shelf"),
            ft.dropdown.Option("1", "High Shelf"),
            ft.dropdown.Option("2", "Peaking"),
        ],
        value="0",
        width=150,
    )
    v_eq_val = ft.Slider(min=-20, max=20, divisions=40, value=-2.0, label="{value} dB")
    
    v_ultra = ft.Checkbox(label="Ultra Sonic Filter", value=False)
    v_ultra_freq = ft.TextField(value="21000", width=100, label="Freq Hz")
    v_ultra_level = ft.Slider(min=0.0001, max=0.01, divisions=100, value=0.001, label="{value}")
    
    v_haas = ft.Checkbox(label="Haas Effect", value=False)
    v_haas_val = ft.Slider(min=0, max=40, divisions=40, value=15.0, label="{value} ms")
    
    v_dither = ft.Checkbox(label="Dither", value=False)
    v_dither_method = ft.Dropdown(
        options=[
            ft.dropdown.Option("triangular_hp", "Triangular HP"),
            ft.dropdown.Option("rectangular", "Rectangular"),
            ft.dropdown.Option("noise_shaping", "Noise Shaping"),
        ],
        value="triangular_hp",
        width=150,
    )
    
    v_trim = ft.Checkbox(label="Trim Silence", value=False)
    v_trim_val = ft.Slider(min=0, max=60, divisions=60, value=5.0, label="{value} sec")
    
    v_fade = ft.Checkbox(label="Fade In/Out", value=False)
    v_fade_val = ft.Slider(min=0, max=30, divisions=30, value=5.0, label="{value} sec")
    
    v_preserve_meta = ft.Checkbox(label="Сохранить метаданные", value=True)
    v_preserve_cover = ft.Checkbox(label="Сохранить обложку", value=True)
    v_delete_orig = ft.Checkbox(label="Удалить оригиналы", value=False)
    
    # Выбор формата и качества
    conv_format = ft.Dropdown(
        options=[ft.dropdown.Option(k, k.upper()) for k in SUPPORTED_FORMATS.keys()],
        value="mp3",
        width=150,
        on_change=lambda e: update_quality_options(),
    )
    
    quality_options = ft.Dropdown(
        options=[ft.dropdown.Option(q, q) for q in QUALITY_PRESETS.get('mp3', [])],
        value="320 kbps (CBR)",
        width=200,
    )
    
    def update_quality_options():
        fmt = conv_format.value
        quality_options.options = [ft.dropdown.Option(q, q) for q in QUALITY_PRESETS.get(fmt, [])]
        if quality_options.options:
            quality_options.value = quality_options.options[0].key
        page.update()
    
    # Текстовые поля для метаданных
    title_field = ft.TextField(label="Title", expand=True)
    artist_field = ft.TextField(label="Artist", expand=True)
    album_field = ft.TextField(label="Album", expand=True)
    year_field = ft.TextField(label="Year", width=100)
    genre_field = ft.TextField(label="Genre", width=150)
    
    # Лог событий
    log_area = ft.TextField(
        multiline=True,
        min_lines=8,
        max_lines=15,
        read_only=True,
        value="FFmpeg: " + ("найден" if state['ffmpeg_ok'] else "НЕ НАЙДЕН"),
        text_size=12,
    )
    
    def log_message(msg, level="info"):
        current = log_area.value
        timestamp = timedelta(seconds=int(threading.current_thread().ident % 10000)).__str__()
        prefix = "[INFO]" if level == "info" else "[ERROR]" if level == "error" else "[OK]"
        new_line = f"{prefix} {msg}"
        lines = current.split('\n')
        lines.append(new_line)
        if len(lines) > 100:
            lines = lines[-100:]
        log_area.value = '\n'.join(lines)
        log_area.scroll_to_end()
        page.update()
    
    # Waveform виджеты
    waveform_before = WaveformCanvas("ДО изменений", "#5599ff", "#0d1117")
    waveform_after = WaveformCanvas("ПОСЛЕ изменений", "#44dd44", "#0d170d")
    
    def load_waveform(file_path):
        """Загрузка waveform для файла"""
        log_message(f"Загрузка waveform: {os.path.basename(file_path)}")
        
        def _load():
            try:
                cmd = ['ffmpeg', '-i', file_path, '-f', 's16le', '-ac', '1', '-ar', '500', '-']
                res = subprocess.run(cmd, capture_output=True, timeout=60)
                if res.returncode == 0 and res.stdout:
                    n = len(res.stdout) // 2
                    raw = struct.unpack(f'{n}h', res.stdout)
                    samples = [s / 32768.0 for s in raw]
                    
                    def _update():
                        waveform_before.set_samples(samples)
                        state['waveform_samples'] = samples
                        compute_preview()
                    
                    page.run_task(_update)
                else:
                    page.run_task(lambda: log_message("Ошибка декодирования аудио", "error"))
            except Exception as e:
                page.run_task(lambda: log_message(f"Ошибка: {e}", "error"))
        
        threading.Thread(target=_load, daemon=True).start()
    
    def compute_preview():
        """Вычисление preview после изменений (упрощенная версия)"""
        if not state.get('waveform_samples'):
            return
        
        log_message("Вычисление preview...")
        # В полной версии здесь применялись бы фильтры
        # Для демонстрации просто копируем существующий waveform
        import time
        time.sleep(0.5)
        page.run_task(lambda: waveform_after.set_samples(state['waveform_samples']))
    
    def pick_files(e):
        """Выбор файлов"""
        # В Flet нет стандартного диалога выбора файлов в desktop режиме
        # Используем file_picker
        dialog = ft.FilePicker(on_result=lambda e: on_files_picked(e), allow_multiple=True)
        page.overlay.append(dialog)
        dialog.pick_files(allowed_extensions=["mp3", "flac", "wav", "ogg", "aac", "m4a"])
        page.update()
    
    def on_files_picked(e):
        """Обработка выбранных файлов"""
        if e.files:
            for f in e.files:
                if f.path not in state['input_files']:
                    state['input_files'].append(f.path)
                    try:
                        info = TrackInfo(f.path)
                        state['tracks_info'].append(info)
                    except Exception as ex:
                        log_message(f"Ошибка чтения {f.name}: {ex}", "error")
            
            update_file_list()
            if state['input_files'] and state['current_index'] == -1:
                state['current_index'] = 0
                select_file(0)
    
    def update_file_list():
        """Обновление списка файлов"""
        files_list.controls.clear()
        for i, path in enumerate(state['input_files']):
            name = os.path.basename(path)
            is_selected = i == state['current_index']
            files_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.icons.AUDIO_FILE, color="amber" if is_selected else "grey"),
                    title=ft.Text(name, size=12, color="white" if is_selected else None),
                    selected=is_selected,
                    on_click=lambda e, idx=i: select_file(idx),
                )
            )
        page.update()
    
    def select_file(index):
        """Выбор файла из списка"""
        if 0 <= index < len(state['input_files']):
            state['current_index'] = index
            update_file_list()
            load_waveform(state['input_files'][index])
    
    def pick_output_dir(e):
        """Выбор директории вывода"""
        dialog = ft.FilePicker(on_result=lambda e: on_dir_picked(e))
        page.overlay.append(dialog)
        dialog.get_directory_path()
        page.update()
    
    def on_dir_picked(e):
        """Обработка выбранной директории"""
        if e.path:
            state['output_dir'] = e.path
            log_message(f"Output dir: {state['output_dir']}")
    
    def start_processing(e):
        """Запуск обработки"""
        if not state['input_files']:
            log_message("Нет файлов для обработки", "error")
            return
        
        if not state['ffmpeg_ok']:
            log_message("FFmpeg не найден", "error")
            return
        
        # Сбор настроек
        settings = {
            'pitch_shift': v_pitch.value,
            'pitch_value': v_pitch_val.value,
            'speed_change': v_speed.value,
            'speed_value': v_speed_val.value,
            'eq': v_eq.value,
            'eq_type': int(v_eq_type.value),
            'eq_value': v_eq_val.value,
            'ultra_sonic': v_ultra.value,
            'ultra_freq': float(v_ultra_freq.value or 21000),
            'ultra_level': v_ultra_level.value,
            'haas': v_haas.value,
            'haas_delay': v_haas_val.value,
            'dither': v_dither.value,
            'dither_method': v_dither_method.value,
            'trim': v_trim.value,
            'trim_threshold': v_trim_val.value,
            'fade': v_fade.value,
            'fade_duration': v_fade_val.value,
            'preserve_metadata': v_preserve_meta.value,
            'preserve_cover': v_preserve_cover.value,
            'delete_original': v_delete_orig.value,
            'output_format': conv_format.value,
            'quality': quality_options.value,
        }
        
        metadata = {
            'title': title_field.value,
            'artist': artist_field.value,
            'album': album_field.value,
            'year': year_field.value,
            'genre': genre_field.value,
        }
        
        log_message(f"Запуск обработки {len(state['input_files'])} файлов...")
        
        # Запуск worker в отдельном потоке
        def run_worker():
            success_count = 0
            for i, file_path in enumerate(state['input_files']):
                try:
                    # Упрощенная обработка - в реальности нужно использовать ModificationWorker
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    output_name = f"{base_name}_modified.{conv_format.value}"
                    output_path = os.path.join(state['output_dir'], output_name)
                    
                    # Обеспечиваем существование директории
                    os.makedirs(state['output_dir'], exist_ok=True)
                    
                    # Пример команды ffmpeg (упрощенно)
                    cmd = ['ffmpeg', '-i', file_path, '-y', output_path]
                    result = subprocess.run(cmd, capture_output=True, timeout=300)
                    
                    if result.returncode == 0:
                        success_count += 1
                        page.run_task(lambda p=output_path: log_message(f"Готово: {os.path.basename(p)}", "ok"))
                    else:
                        page.run_task(lambda f=file_path: log_message(f"Ошибка: {os.path.basename(f)}", "error"))
                        
                except Exception as ex:
                    page.run_task(lambda f=file_path, e=str(ex): log_message(f"Ошибка {os.path.basename(f)}: {e}", "error"))
            
            page.run_task(lambda: log_message(f"Обработка завершена. Успешно: {success_count}/{len(state['input_files'])}", "ok"))
        
        threading.Thread(target=run_worker, daemon=True).start()
    
    def clear_all(e):
        """Очистка всего"""
        state['input_files'] = []
        state['tracks_info'] = []
        state['current_index'] = -1
        state['waveform_samples'] = None
        files_list.controls.clear()
        waveform_before.set_samples([])
        waveform_after.set_samples([])
        log_area.value = "Очищено"
        page.update()
    
    # Список файлов
    files_list = ft.ListView(expand=True, spacing=2, selection_mode=None)
    
    # Основная компоновка
    page.add(
        ft.Row([
            ft.Text("VK Modifier", size=20, weight=ft.FontWeight.BOLD, color="indigo"),
            ft.Container(width=20),
            ft.FilledButton("📁 Добавить файлы", on_click=pick_files),
            ft.FilledButton("📂 Вывод", on_click=pick_output_dir),
            ft.FilledButton("▶ Старт", on_click=start_processing, bgcolor="green"),
            ft.FilledButton("🗑 Очистить", on_click=clear_all, variant=ft.ButtonVariant.OUTLINE),
        ], alignment=ft.MainAxisAlignment.START),
        
        ft.Divider(),
        
        ft.Row([
            # Левая панель - список файлов
            ft.Container(
                content=ft.Column([
                    ft.Text("Файлы", weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=files_list,
                        height=300,
                        border=ft.border.all(1, "#333"),
                        border_radius=5,
                        padding=5,
                    ),
                ]),
                width=300,
            ),
            
            # Центральная панель - параметры
            ft.Container(
                content=ft.Column([
                    ft.Text("Параметры обработки", weight=ft.FontWeight.BOLD),
                    ft.Expander(
                        content=ft.Column([
                            v_pitch, v_pitch_val,
                            v_speed, v_speed_val,
                        ], spacing=5),
                        label="Pitch & Speed",
                    ),
                    ft.Expander(
                        content=ft.Column([
                            v_eq, v_eq_type, v_eq_val,
                        ], spacing=5),
                        label="EQ",
                    ),
                    ft.Expander(
                        content=ft.Column([
                            v_ultra, 
                            ft.Row([v_ultra_freq, ft.Text("Hz")]),
                            v_ultra_level,
                        ], spacing=5),
                        label="Ultra Sonic",
                    ),
                    ft.Expander(
                        content=ft.Column([
                            v_haas, v_haas_val,
                            v_dither, v_dither_method,
                        ], spacing=5),
                        label="Spatial & Dither",
                    ),
                    ft.Expander(
                        content=ft.Column([
                            v_trim, v_trim_val,
                            v_fade, v_fade_val,
                        ], spacing=5),
                        label="Edit",
                    ),
                    ft.Divider(),
                    ft.Text("Метаданные", weight=ft.FontWeight.BOLD, size=12),
                    ft.Row([title_field, artist_field]),
                    ft.Row([album_field, year_field, genre_field]),
                    ft.Row([v_preserve_meta, v_preserve_cover, v_delete_orig]),
                    ft.Divider(),
                    ft.Text("Конвертация", weight=ft.FontWeight.BOLD, size=12),
                    ft.Row([ft.Text("Формат:"), conv_format, quality_options]),
                ], scroll=ft.ScrollMode.AUTO),
                expand=True,
                padding=10,
            ),
            
            # Правая панель - waveform
            ft.Container(
                content=ft.Column([
                    ft.Text("Визуализация", weight=ft.FontWeight.BOLD),
                    ft.Row([waveform_before, waveform_after], expand=True),
                ]),
                width=500,
            ),
        ], expand=True),
        
        ft.Divider(),
        
        # Лог
        ft.Container(
            content=log_area,
            height=150,
            border=ft.border.all(1, "#333"),
            border_radius=5,
        ),
    )
    
    # Инициализация
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
