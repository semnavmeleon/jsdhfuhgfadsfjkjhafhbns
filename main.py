import flet as ft
import asyncio
import os
import random
import json
import tempfile
import threading
import queue
import struct
import math
import subprocess
import re
import hashlib
from datetime import timedelta, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Конфигурация
CONFIG_FILE = "vk_modifier_config.json"
SUPPORTED_FORMATS = {
    'mp3': 'MP3 (lossy)',
    'flac': 'FLAC (lossless)',
    'wav': 'WAV (lossless)',
    'ogg': 'OGG Vorbis (lossy)',
    'aac': 'AAC (lossy)',
    'm4a': 'M4A AAC (lossy)',
    'wma': 'WMA (lossy)',
    'opus': 'Opus (lossy)',
    'aiff': 'AIFF (lossless)',
    'alac': 'ALAC (lossless)',
    'wv': 'WavPack (lossless/hybrid)',
    'ape': "Monkey's Audio (lossless)",
    'tta': 'True Audio (lossless)',
    'ac3': 'AC3/Dolby Digital (lossy)',
    'dts': 'DTS (lossy)',
    'mp2': 'MPEG Layer 2 (lossy)',
    'mpc': 'Musepack (lossy)',
    'spx': 'Speex (speech)',
    'amr': 'AMR (speech)',
    'au': 'AU/Sun Audio (uncompressed)',
    'mka': 'Matroska Audio (container)',
    'oga': 'Ogg FLAC (lossless)',
    'caf': 'Core Audio Format (uncompressed)',
    'shn': 'Shorten (lossless)',
}

QUALITY_PRESETS = {
    'mp3': ['320 kbps (CBR)', '256 kbps (CBR)', '192 kbps (CBR)', '128 kbps (CBR)', 'VBR Высшее (Q0)', 'VBR Высокое (Q2)', 'VBR Среднее (Q4)', 'VBR Низкое (Q6)'],
    'aac': ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
    'm4a': ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
    'ogg': ['Качество 10 (макс)', 'Качество 8 (высокое)', 'Качество 6 (среднее)', 'Качество 4 (низкое)', 'Качество 2 (мин)'],
    'opus': ['256 kbps', '192 kbps', '128 kbps', '96 kbps', '64 kbps'],
    'wma': ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
}

FORMAT_CODECS = {
    'mp3': 'libmp3lame',
    'flac': 'flac',
    'wav': 'pcm_s16le',
    'ogg': 'libvorbis',
    'aac': 'aac',
    'm4a': 'aac',
    'wma': 'wmav2',
    'opus': 'libopus',
    'aiff': 'pcm_s16be',
    'alac': 'alac',
    'wv': 'wavpack',
    'ape': 'ape',
    'tta': 'tta',
    'ac3': 'ac3',
    'dts': 'dts',
    'mp2': 'mp2',
    'mpc': 'mpc',
    'spx': 'libspeex',
    'amr': 'libopencore_amrnb',
    'au': 'pcm_s16be',
    'mka': 'libvorbis',
    'oga': 'flac',
    'caf': 'pcm_s16le',
    'shn': 'shorten',
}

INPUT_EXTENSIONS = [
    ("Все аудио файлы", ".mp3 .flac .wav .ogg .aac .m4a .wma .opus .aiff .alac .wv .ape .tta .ac3 .dts .mp2 .mpc .spx .amr .au .mka .oga .caf .shn"),
    ("MP3 files", ".mp3"), ("FLAC files", ".flac"), ("WAV files", ".wav"),
    ("OGG files", ".ogg"), ("AAC files", ".aac"), ("M4A files", ".m4a"),
    ("WMA files", ".wma"), ("Opus files", ".opus"), ("AIFF files", ".aiff"),
    ("ALAC files", ".alac"), ("WavPack files", ".wv"), ("Monkey's Audio files", ".ape"),
    ("True Audio files", ".tta"), ("AC3 files", ".ac3"), ("DTS files", ".dts"),
    ("MP2 files", ".mp2"), ("Musepack files", ".mpc"), ("Speex files", ".spx"),
    ("AMR files", ".amr"), ("AU files", ".au"), ("Matroska Audio files", ".mka"),
    ("Ogg FLAC files", ".oga"), ("CAF files", ".caf"), ("Shorten files", ".shn"),
]


class TrackInfo:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.size_mb = os.path.getsize(file_path) / (1024 * 1024)
        self.duration_sec = 0
        self.title = ""
        self.artist = ""
        self.album = ""
        self.year = ""
        self.genre = ""
        self.cover_data = None
        self.cover_mime = "image/jpeg"
        self.bitrate = 0
        self.sample_rate = 0
        self._load_metadata()

    def _load_metadata(self):
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3
            audio = MP3(self.file_path)
            self.duration_sec = audio.info.length
            self.bitrate = audio.info.bitrate // 1000
            self.sample_rate = audio.info.sample_rate
        except:
            pass
        try:
            from mutagen.id3 import ID3
            tags = ID3(self.file_path)
            self.title = str(tags.get('TIT2', ''))
            self.artist = str(tags.get('TPE1', ''))
            self.album = str(tags.get('TALB', ''))
            self.year = str(tags.get('TDRC', ''))
            self.genre = str(tags.get('TCON', ''))
            for key in tags:
                if key.startswith('APIC'):
                    self.cover_data = tags[key].data
                    self.cover_mime = tags[key].mime
                    break
        except:
            pass


class BatchConverter:
    def __init__(self, files, output_dir, output_format, quality_preset,
                 result_queue, max_workers=4, delete_originals=False):
        self.files = files
        self.output_dir = output_dir
        self.output_format = output_format
        self.quality_preset = quality_preset
        self.queue = result_queue
        self.max_workers = max_workers
        self.delete_originals = delete_originals
        self._success_count = 0
        self._lock = threading.Lock()

    def run_in_thread(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _get_ffmpeg_args(self, input_path, output_path):
        codec = self._get_codec()
        args = ['ffmpeg', '-i', input_path]

        if self.output_format == 'mp3':
            if 'CBR' in self.quality_preset:
                bitrate = self.quality_preset.split()[0]
                args.extend(['-codec:a', codec, '-b:a', f'{bitrate}k'])
            else:
                if 'Q0' in self.quality_preset:
                    args.extend(['-codec:a', codec, '-q:a', '0'])
                elif 'Q2' in self.quality_preset:
                    args.extend(['-codec:a', codec, '-q:a', '2'])
                elif 'Q4' in self.quality_preset:
                    args.extend(['-codec:a', codec, '-q:a', '4'])
                elif 'Q6' in self.quality_preset:
                    args.extend(['-codec:a', codec, '-q:a', '6'])
                else:
                    args.extend(['-codec:a', codec, '-q:a', '0'])
        elif self.output_format in ['aac', 'm4a', 'opus', 'wma']:
            bitrate = self.quality_preset.split()[0]
            args.extend(['-codec:a', codec, '-b:a', f'{bitrate}k'])
        elif self.output_format == 'ogg':
            if '10' in self.quality_preset:
                args.extend(['-codec:a', codec, '-q:a', '10'])
            elif '8' in self.quality_preset:
                args.extend(['-codec:a', codec, '-q:a', '8'])
            elif '6' in self.quality_preset:
                args.extend(['-codec:a', codec, '-q:a', '6'])
            elif '4' in self.quality_preset:
                args.extend(['-codec:a', codec, '-q:a', '4'])
            elif '2' in self.quality_preset:
                args.extend(['-codec:a', codec, '-q:a', '2'])
            else:
                args.extend(['-codec:a', codec, '-q:a', '6'])
        elif self.output_format == 'flac':
            if 'Compression' in self.quality_preset:
                comp = self.quality_preset.split()[-1]
                args.extend(['-codec:a', codec, '-compression_level', comp])
            else:
                args.extend(['-codec:a', codec])
        elif self.output_format in ['wav', 'aiff', 'alac', 'wv', 'ape', 'tta', 'au', 'oga', 'caf', 'shn']:
            args.extend(['-codec:a', codec])
        elif self.output_format == 'ac3':
            args.extend(['-codec:a', codec, '-b:a', '448k'])
        elif self.output_format == 'dts':
            args.extend(['-codec:a', codec, '-b:a', '1536k'])
        elif self.output_format == 'mp2':
            args.extend(['-codec:a', codec, '-b:a', '256k'])
        elif self.output_format == 'mpc':
            args.extend(['-codec:a', codec, '-q:a', '7'])
        elif self.output_format == 'spx':
            args.extend(['-codec:a', codec, '-q:a', '8'])
        elif self.output_format == 'amr':
            args.extend(['-codec:a', codec, '-ar', '8000', '-ac', '1', '-b:a', '12.2k'])
        elif self.output_format == 'mka':
            args.extend(['-codec:a', codec, '-q:a', '6'])
        else:
            args.extend(['-codec:a', 'libmp3lame', '-b:a', '320k'])

        args.extend(['-y', output_path])
        return args

    def _get_codec(self):
        codecs = {
            'mp3': 'libmp3lame', 'flac': 'flac', 'wav': 'pcm_s16le',
            'ogg': 'libvorbis', 'aac': 'aac', 'm4a': 'aac',
            'wma': 'wmav2', 'opus': 'libopus', 'aiff': 'pcm_s16be',
            'alac': 'alac', 'wv': 'wavpack', 'ape': 'ape',
            'tta': 'tta', 'ac3': 'ac3', 'dts': 'dts',
            'mp2': 'mp2', 'mpc': 'mpc', 'spx': 'libspeex',
            'amr': 'libopencore_amrnb', 'au': 'pcm_s16be',
            'mka': 'libvorbis', 'oga': 'flac', 'caf': 'pcm_s16le',
            'shn': 'shorten'
        }
        return codecs.get(self.output_format, 'libmp3lame')

    def _process_one(self, idx, file_path):
        total = len(self.files)
        self.queue.put(('progress', idx + 1, total, file_path))

        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_name = f"{base_name}.{self.output_format}"
            output_path = os.path.join(self.output_dir, output_name)

            counter = 1
            while os.path.exists(output_path):
                output_name = f"{base_name}_{counter}.{self.output_format}"
                output_path = os.path.join(self.output_dir, output_name)
                counter += 1

            args = self._get_ffmpeg_args(file_path, output_path)
            result = subprocess.run(args, capture_output=True, encoding='utf-8', errors='ignore', timeout=300)

            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                if self.delete_originals:
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass
                with self._lock:
                    self._success_count += 1
                self.queue.put(('file_done', file_path, True, output_path))
            else:
                self.queue.put(('file_done', file_path, False, ""))
        except Exception as e:
            self.queue.put(('file_done', file_path, False, ""))
            self.queue.put(('error', f"Ошибка конвертации {os.path.basename(file_path)}: {str(e)}"))

    def _run(self):
        total = len(self.files)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_one, i, fp): i
                for i, fp in enumerate(self.files)
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.queue.put(('error', str(e)))
        self.queue.put(('all_done', self._success_count, total))


class VKModifierApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "VK Modifier"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 1400
        self.page.window.height = 950
        self.page.window.min_width = 1000
        self.page.window.min_height = 800
        
        # Данные
        self.input_files = []
        self.tracks_info = []
        self.current_index = -1
        self.output_dir = os.path.expanduser("~/Desktop/Output")
        self.saved_presets = []
        self.user_templates = []
        self.selected_cover_path = None
        self._cover_is_temp = False
        self._worker_queue = queue.Queue()
        self._completed_count = 0
        self._mode = 'modifier'
        
        # Переменные состояния
        self._init_vars()
        
        # Загрузка конфига
        self._load_config()
        
        # Проверка FFmpeg
        self.ffmpeg_ok = self._check_ffmpeg()
        
        # Построение UI
        self._build_ui()
        
        # Запуск polling очереди
        self._start_queue_polling()
        
        # Обновление UI после загрузки
        self.page.update()

    def _init_vars(self):
        # Основные методы
        self.v_pitch = False
        self.v_pitch_val = 0.5
        self.v_speed = False
        self.v_speed_val = 1.00
        self.v_eq = False
        self.v_eq_type = 0
        self.v_eq_val = -2.0
        self.v_silence = False
        self.v_silence_val = 45
        self.v_phase_inv = False
        self.v_phase_inv_val = 1.0
        self.v_phase_scr = False
        self.v_phase_scr_val = 2.0
        self.v_dc = False
        self.v_dc_val = 0.000005
        self.v_resamp = False
        self.v_resamp_val = 1
        self.v_ultra = False
        self.v_ultra_freq = 21000
        self.v_ultra_level = 0.001
        self.v_haas = False
        self.v_haas_val = 15.0
        self.v_dither = False
        self.v_dither_method = 'triangular_hp'
        self.v_id3pad = False
        self.v_id3pad_val = 512
        self.v_trim = False
        self.v_trim_val = 5.0
        self.v_cut = False
        self.v_cut_pos = 50
        self.v_cut_dur = 2.0
        self.v_fade = False
        self.v_fade_val = 5.0
        self.v_merge = False
        self.v_extra = ""
        self.v_broken = False
        self.v_broken_t = 0
        self.v_bitrate_j = False
        self.v_frame_sh = False
        self.v_fake_meta = False
        self.v_reorder = False
        self.v_preserve_meta = False
        self.v_preserve_cover = False
        self.v_rename = True
        self.v_delete_orig = False
        self.v_quality = '320 kbps (CBR)'
        self.v_title = ""
        self.v_artist = ""
        self.v_album = ""
        self.v_year = ""
        self.v_genre = ""
        self.v_filename_template = 'VK_{n:03d}_custom'
        self.v_max_workers = 4
        self.v_thread_delay = 0.0
        
        # Текстурные методы
        self.v_spectral_mask = False
        self.v_spectral_mask_sens = 0.8
        self.v_spectral_mask_att = 12
        self.v_spectral_mask_peaks = 10
        self.v_concert_emu = False
        self.v_concert_intensity = 'medium'
        self.v_midside = False
        self.v_midside_mid = -3.0
        self.v_midside_side = 2.0
        self.v_psycho_noise = False
        self.v_psycho_intensity = 0.0003
        self.v_saturation = False
        self.v_saturation_drive = 1.5
        self.v_saturation_mix = 0.15
        self.v_temp_jitter = False
        self.v_jitter_intensity = 0.002
        self.v_jitter_freq = 0.5
        self.v_spec_jitter = False
        self.v_spec_jitter_count = 5.0
        self.v_spec_jitter_att = 15.0
        self.v_spec_jitter_mode = 'random'
        self.v_spec_jitter_fixed_freqs = ''
        self.v_spec_jitter_manual_freqs = ''
        self.v_spec_jitter_manual_atts = ''
        self.v_spec_jitter_manual_widths = ''
        self.v_spec_jitter_fixed_width = 0.2
        
        # VK Инфразвук
        self.v_vk_infra = False
        self.v_vk_infra_mode = 'modulated'
        self.v_vk_infra_amplitude = 0.35
        self.v_vk_infra_freq = 18.0
        self.v_vk_infra_mod_freq = 0.08
        self.v_vk_infra_mod_depth = 0.3
        self.v_vk_infra_phase_shift = 0.0
        self.v_vk_infra_waveform = 'sine'
        self.v_vk_infra_adaptive = False
        self.v_vk_infra_h1 = 0.15
        self.v_vk_infra_h2 = 0.07
        self.v_vk_infra_h3 = 0.03
        
        # Конвертер
        self.v_conv_format = 'mp3'
        self.v_conv_quality = '320 kbps (CBR)'
        self.v_conv_delete = False

    def _check_ffmpeg(self):
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except Exception:
            return False

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.output_dir = cfg.get('output_dir', self.output_dir)
                self.saved_presets = cfg.get('presets', [])
                self.user_templates = cfg.get('user_templates', [])
                
                settings = cfg.get('settings', {})
                if settings:
                    for key, value in settings.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
        except Exception:
            pass

    def _save_config(self):
        try:
            settings = {
                'output_dir': self.output_dir,
                'v_pitch': self.v_pitch, 'v_pitch_val': self.v_pitch_val,
                'v_speed': self.v_speed, 'v_speed_val': self.v_speed_val,
                'v_eq': self.v_eq, 'v_eq_type': self.v_eq_type, 'v_eq_val': self.v_eq_val,
                'v_silence': self.v_silence, 'v_silence_val': self.v_silence_val,
                'v_phase_inv': self.v_phase_inv, 'v_phase_inv_val': self.v_phase_inv_val,
                'v_phase_scr': self.v_phase_scr, 'v_phase_scr_val': self.v_phase_scr_val,
                'v_dc': self.v_dc, 'v_dc_val': self.v_dc_val,
                'v_resamp': self.v_resamp, 'v_resamp_val': self.v_resamp_val,
                'v_ultra': self.v_ultra, 'v_ultra_freq': self.v_ultra_freq, 'v_ultra_level': self.v_ultra_level,
                'v_haas': self.v_haas, 'v_haas_val': self.v_haas_val,
                'v_dither': self.v_dither, 'v_dither_method': self.v_dither_method,
                'v_id3pad': self.v_id3pad, 'v_id3pad_val': self.v_id3pad_val,
                'v_trim': self.v_trim, 'v_trim_val': self.v_trim_val,
                'v_cut': self.v_cut, 'v_cut_pos': self.v_cut_pos, 'v_cut_dur': self.v_cut_dur,
                'v_fade': self.v_fade, 'v_fade_val': self.v_fade_val,
                'v_merge': self.v_merge, 'v_extra': self.v_extra,
                'v_broken': self.v_broken, 'v_broken_t': self.v_broken_t,
                'v_bitrate_j': self.v_bitrate_j, 'v_frame_sh': self.v_frame_sh,
                'v_fake_meta': self.v_fake_meta, 'v_reorder': self.v_reorder,
                'v_preserve_meta': self.v_preserve_meta, 'v_preserve_cover': self.v_preserve_cover,
                'v_rename': self.v_rename, 'v_delete_orig': self.v_delete_orig,
                'v_quality': self.v_quality, 'v_title': self.v_title,
                'v_artist': self.v_artist, 'v_album': self.v_album,
                'v_year': self.v_year, 'v_genre': self.v_genre,
                'v_filename_template': self.v_filename_template,
                'v_max_workers': self.v_max_workers, 'v_thread_delay': self.v_thread_delay,
                'v_spectral_mask': self.v_spectral_mask, 'v_spectral_mask_sens': self.v_spectral_mask_sens,
                'v_spectral_mask_att': self.v_spectral_mask_att, 'v_spectral_mask_peaks': self.v_spectral_mask_peaks,
                'v_concert_emu': self.v_concert_emu, 'v_concert_intensity': self.v_concert_intensity,
                'v_midside': self.v_midside, 'v_midside_mid': self.v_midside_mid, 'v_midside_side': self.v_midside_side,
                'v_psycho_noise': self.v_psycho_noise, 'v_psycho_intensity': self.v_psycho_intensity,
                'v_saturation': self.v_saturation, 'v_saturation_drive': self.v_saturation_drive, 'v_saturation_mix': self.v_saturation_mix,
                'v_temp_jitter': self.v_temp_jitter, 'v_jitter_intensity': self.v_jitter_intensity, 'v_jitter_freq': self.v_jitter_freq,
                'v_spec_jitter': self.v_spec_jitter, 'v_spec_jitter_count': self.v_spec_jitter_count,
                'v_spec_jitter_att': self.v_spec_jitter_att, 'v_spec_jitter_mode': self.v_spec_jitter_mode,
                'v_spec_jitter_fixed_freqs': self.v_spec_jitter_fixed_freqs,
                'v_spec_jitter_manual_freqs': self.v_spec_jitter_manual_freqs,
                'v_spec_jitter_manual_atts': self.v_spec_jitter_manual_atts,
                'v_spec_jitter_manual_widths': self.v_spec_jitter_manual_widths,
                'v_spec_jitter_fixed_width': self.v_spec_jitter_fixed_width,
                'v_vk_infra': self.v_vk_infra, 'v_vk_infra_mode': self.v_vk_infra_mode,
                'v_vk_infra_amplitude': self.v_vk_infra_amplitude, 'v_vk_infra_freq': self.v_vk_infra_freq,
                'v_vk_infra_mod_freq': self.v_vk_infra_mod_freq, 'v_vk_infra_mod_depth': self.v_vk_infra_mod_depth,
                'v_vk_infra_phase_shift': self.v_vk_infra_phase_shift, 'v_vk_infra_waveform': self.v_vk_infra_waveform,
                'v_vk_infra_adaptive': self.v_vk_infra_adaptive, 'v_vk_infra_h1': self.v_vk_infra_h1,
                'v_vk_infra_h2': self.v_vk_infra_h2, 'v_vk_infra_h3': self.v_vk_infra_h3,
                'v_conv_format': self.v_conv_format, 'v_conv_quality': self.v_conv_quality,
                'v_conv_delete': self.v_conv_delete,
            }
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'output_dir': self.output_dir,
                    'presets': self.saved_presets,
                    'user_templates': self.user_templates,
                    'settings': settings
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")

    def _safe_filename(self, s):
        return re.sub(r'[\\/*?:"<>|]', '_', str(s)).strip() or '_'

    def _log(self, message, level='info', to_converter=False):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_text = f"[{timestamp}] {message}\n"
        
        if to_converter:
            if hasattr(self, 'conv_log_text'):
                self.conv_log_text.value += log_text
                self.conv_log_text.update()
        else:
            if hasattr(self, 'log_text'):
                self.log_text.value += log_text
                self.log_text.update()

    def _build_ui(self):
        # Заголовок
        header = ft.Container(
            content=ft.Row([
                ft.Text("VK Modifier", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(width=20),
                ft.FilledButton("Модификатор", on_click=lambda e: self._switch_mode('modifier')),
                ft.FilledButton("Конвертер", on_click=lambda e: self._switch_mode('converter')),
                ft.Text("Режим: Модификатор", size=14, color=ft.Colors.BLUE_400),
                ft.Text(f"FFmpeg: {'найден' if self.ffmpeg_ok else 'НЕ НАЙДЕН'}", 
                       color=ft.Colors.GREEN if self.ffmpeg_ok else ft.Colors.RED),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=10,
            bgcolor=ft.Colors.GREY_900
        )
        self.page.add(header)
        
        # Основной контент
        self.main_content = ft.Column([], expand=True, spacing=10)
        self.page.add(self.main_content)
        
        # Создаём оба режима
        self.modifier_content = self._build_modifier_interface()
        self.converter_content = self._build_converter_interface()
        
        # Показываем модификатор
        self.main_content.controls.append(self.modifier_content)
        self.converter_content.visible = False
        self.main_content.controls.append(self.converter_content)
        
        self.page.update()

    def _switch_mode(self, mode):
        self._mode = mode
        if mode == 'modifier':
            self.modifier_content.visible = True
            self.converter_content.visible = False
        else:
            self.modifier_content.visible = False
            self.converter_content.visible = True
        
        self._clear_files()
        self.page.update()

    def _build_modifier_interface(self):
        container = ft.Container(
            content=ft.Column([
                self._build_file_section(),
                self._build_settings_tabs(),
                self._build_output_section(),
                self._build_action_section(),
                self._build_log_section(),
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            expand=True,
            padding=10
        )
        return container

    def _build_file_section(self):
        self.file_listbox = ft.ListView(expand=True, height=200, spacing=2)
        
        file_controls = ft.Row([
            ft.FilledButton("Добавить файлы", on_click=lambda e: self._add_files_dialog()),
            ft.FilledButton("Очистить", on_click=lambda e: self._clear_files()),
            ft.FilledButton("Удалить выбранный", on_click=lambda e: self._remove_selected(), disabled=True),
        ], spacing=10)
        
        self.lbl_stats = ft.Text("0 файлов | 0.0 MB", size=12)
        
        return ft.Container(
            content=ft.Column([
                file_controls,
                self.file_listbox,
                self.lbl_stats,
            ], spacing=5),
            padding=10,
            border=ft.Border(
                top=ft.BorderSide(1, ft.Colors.OUTLINE),
                bottom=ft.BorderSide(1, ft.Colors.OUTLINE),
                left=ft.BorderSide(1, ft.Colors.OUTLINE),
                right=ft.BorderSide(1, ft.Colors.OUTLINE)
            ),
            border_radius=10
        )

    def _build_settings_tabs(self):
        # Создаём вкладки без content
        tab_list = [
            ft.Tab(label="Базовые"),
            ft.Tab(label="Спектральные"),
            ft.Tab(label="Текстурные"),
            ft.Tab(label="Дополнительные"),
            ft.Tab(label="Метаданные"),
            ft.Tab(label="Имена файлов"),
            ft.Tab(label="Технические"),
            ft.Tab(label="Системные"),
        ]
        self.tabs = ft.Tabs(
            tabs=tab_list,
            selected_index=0,
            expand=1,
            on_change=self._on_tab_changed
        )
        
        # Контейнер для динамического контента
        self.tab_content = ft.Container(
            content=self._build_basic_tab(),  # по умолчанию первая вкладка
            expand=True,
            padding=5
        )
        
        return ft.Container(
            content=ft.Column([self.tabs, self.tab_content], expand=True),
            expand=True
        )

    def _on_tab_changed(self, e):
        """Обработчик смены вкладки"""
        selected = e.control.selected_index
        if selected == 0:
            self.tab_content.content = self._build_basic_tab()
        elif selected == 1:
            self.tab_content.content = self._build_spectral_tab()
        elif selected == 2:
            self.tab_content.content = self._build_texture_tab()
        elif selected == 3:
            self.tab_content.content = self._build_advanced_tab()
        elif selected == 4:
            self.tab_content.content = self._build_metadata_tab()
        elif selected == 5:
            self.tab_content.content = self._build_filename_tab()
        elif selected == 6:
            self.tab_content.content = self._build_technical_tab()
        elif selected == 7:
            self.tab_content.content = self._build_system_tab()
        self.page.update()

    def _build_basic_tab(self):
        controls = []
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Изменить тональность (Pitch Shift)", value=self.v_pitch,
                        on_change=lambda e: setattr(self, 'v_pitch', e.control.value)),
                ft.Slider(min=-5, max=5, value=self.v_pitch_val, width=200,
                        on_change=lambda e: setattr(self, 'v_pitch_val', e.control.value)),
                ft.Text(f"{self.v_pitch_val:.1f} семитонов", size=12),
            ])
        )
        controls.append(ft.Text("Транспонирует аудио на +/-N полутонов без изменения темпа.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Изменить скорость (Time Stretch)", value=self.v_speed,
                        on_change=lambda e: setattr(self, 'v_speed', e.control.value)),
                ft.Slider(min=0.9, max=1.1, value=self.v_speed_val, width=200,
                        on_change=lambda e: setattr(self, 'v_speed_val', e.control.value)),
                ft.Text(f"{self.v_speed_val:.2f}x", size=12),
            ])
        )
        controls.append(ft.Text("Ускоряет или замедляет трек с сохранением тональности.", size=11, italic=True, color=ft.Colors.GREY))
        
        eq_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="0", text="Стандарт: -2dB на 1 kHz"),
                ft.DropdownOption(key="1", text="Пресет Mid-Cut"),
                ft.DropdownOption(key="2", text="Пресет Air: 8k +3dB"),
            ],
            value=str(self.v_eq_type),
            width=200,
            on_select=lambda e: setattr(self, 'v_eq_type', int(e.control.value) if e.control.value.isdigit() else 0)
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Эквализация (EQ)", value=self.v_eq,
                        on_change=lambda e: setattr(self, 'v_eq', e.control.value)),
                eq_dropdown,
                ft.Slider(min=-12, max=12, value=self.v_eq_val, width=150,
                        on_change=lambda e: setattr(self, 'v_eq_val', e.control.value)),
                ft.Text(f"{self.v_eq_val:.1f} dB", size=12),
            ])
        )
        controls.append(ft.Text("Ослабляет или усиливает выбранную частотную полосу.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Добавить тишину в конец (Silent Pad)", value=self.v_silence,
                        on_change=lambda e: setattr(self, 'v_silence', e.control.value)),
                ft.Slider(min=1, max=300, value=self.v_silence_val, width=200,
                        on_change=lambda e: setattr(self, 'v_silence_val', int(e.control.value))),
                ft.Text(f"{self.v_silence_val} сек", size=12),
            ])
        )
        controls.append(ft.Text("Добавляет тишину в конец файла.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Плавное затухание (сек)", value=self.v_fade,
                        on_change=lambda e: setattr(self, 'v_fade', e.control.value)),
                ft.Slider(min=0.5, max=30, value=self.v_fade_val, width=200, 
                        on_change=lambda e: setattr(self, 'v_fade_val', e.control.value)),
                ft.Text(f"{self.v_fade_val:.1f} сек", size=12),
            ])
        )
        controls.append(ft.Text("Плавное затухание громкости в конце трека.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Обрезать начало (сек)", value=self.v_trim,
                        on_change=lambda e: setattr(self, 'v_trim', e.control.value)),
                ft.Slider(min=0, max=60, value=self.v_trim_val, width=200,
                        on_change=lambda e: setattr(self, 'v_trim_val', e.control.value)),
                ft.Text(f"{self.v_trim_val:.1f} сек", size=12),
            ])
        )
        controls.append(ft.Text("Удаляет указанное количество секунд с начала трека.", size=11, italic=True, color=ft.Colors.GREY))
        
        return ft.Container(content=ft.Column(controls, spacing=8), padding=10)

    def _build_spectral_tab(self):
        controls = []
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Phase Invert", value=self.v_phase_inv,
                        on_change=lambda e: setattr(self, 'v_phase_inv', e.control.value)),
                ft.Slider(min=0, max=1, value=self.v_phase_inv_val, width=200,
                        on_change=lambda e: setattr(self, 'v_phase_inv_val', e.control.value)),
                ft.Text(f"{self.v_phase_inv_val:.1f}", size=12),
            ])
        )
        controls.append(ft.Text("Инвертирует фазу правого канала.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Phase Scramble", value=self.v_phase_scr,
                        on_change=lambda e: setattr(self, 'v_phase_scr', e.control.value)),
                ft.Slider(min=0.1, max=5, value=self.v_phase_scr_val, width=200,
                        on_change=lambda e: setattr(self, 'v_phase_scr_val', e.control.value)),
                ft.Text(f"{self.v_phase_scr_val:.1f} Гц", size=12),
            ])
        )
        controls.append(ft.Text("Синусоидальная модуляция фазы.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="DC Shift", value=self.v_dc,
                        on_change=lambda e: setattr(self, 'v_dc', e.control.value)),
                ft.Text(f"{self.v_dc_val:.6f}", size=12),
            ])
        )
        controls.append(ft.Text("Постоянное смещение сэмплов.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Resample Drift", value=self.v_resamp,
                        on_change=lambda e: setattr(self, 'v_resamp', e.control.value)),
                ft.Slider(min=-100, max=100, value=self.v_resamp_val, width=200,
                        on_change=lambda e: setattr(self, 'v_resamp_val', int(e.control.value))),
                ft.Text(f"{self.v_resamp_val} Гц", size=12),
            ])
        )
        controls.append(ft.Text("Дрейф частоты дискретизации.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Haas Delay", value=self.v_haas,
                        on_change=lambda e: setattr(self, 'v_haas', e.control.value)),
                ft.Slider(min=0, max=50, value=self.v_haas_val, width=200,
                        on_change=lambda e: setattr(self, 'v_haas_val', e.control.value)),
                ft.Text(f"{self.v_haas_val:.1f} мс", size=12),
            ])
        )
        controls.append(ft.Text("Задержка правого канала.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Ultrasonic Noise", value=self.v_ultra,
                        on_change=lambda e: setattr(self, 'v_ultra', e.control.value)),
                ft.Text("Freq: "), ft.TextField(value=str(self.v_ultra_freq), width=60,
                    on_change=lambda e: setattr(self, 'v_ultra_freq', int(e.control.value) if e.control.value else 21000)),
                ft.Text("Hz Level: "), ft.TextField(value=str(self.v_ultra_level), width=60,
                    on_change=lambda e: setattr(self, 'v_ultra_level', float(e.control.value) if e.control.value else 0.001)), 
            ])
        )
        controls.append(ft.Text("Подмешивает неслышимый ультразвук.", size=11, italic=True, color=ft.Colors.GREY))
        
        dither_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="triangular_hp", text="triangular_hp"),
                ft.DropdownOption(key="rectangular", text="rectangular"),
                ft.DropdownOption(key="gaussian", text="gaussian"),
                ft.DropdownOption(key="lipshitz", text="lipshitz"),
            ],
            value=self.v_dither_method,
            width=150,
            on_select=lambda e: setattr(self, 'v_dither_method', e.control.value or "triangular_hp")
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Dither Attack", value=self.v_dither,
                        on_change=lambda e: setattr(self, 'v_dither', e.control.value)),
                dither_dropdown,
            ])
        )
        controls.append(ft.Text("Шум квантования при конвертации в MP3.", size=11, italic=True, color=ft.Colors.GREY))
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="ID3 Padding Attack", value=self.v_id3pad,
                        on_change=lambda e: setattr(self, 'v_id3pad', e.control.value)),
                ft.Slider(min=0, max=2048, value=self.v_id3pad_val, width=200,
                        on_change=lambda e: setattr(self, 'v_id3pad_val', int(e.control.value))),
                ft.Text(f"{self.v_id3pad_val} байт", size=12),
            ])
        )
        controls.append(ft.Text("Мусорные данные в тегах ID3v2.", size=11, italic=True, color=ft.Colors.GREY))
        
        return ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.AUTO), padding=10, height=500)

    def _build_texture_tab(self):
        controls = []
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Спектральное маскирование", value=self.v_spectral_mask,
                        on_change=lambda e: setattr(self, 'v_spectral_mask', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([ 
                ft.Text("Чувствительность: ", width=120),
                ft.Slider(min=0.1, max=2, value=self.v_spectral_mask_sens, width=150,
                        on_change=lambda e: setattr(self, 'v_spectral_mask_sens', e.control.value)),
                ft.Text(f"{self.v_spectral_mask_sens:.1f}", width=50),
                ft.Text("Аттенюация (dB): ", width=120),
                ft.Slider(min=1, max=30, value=self.v_spectral_mask_att, width=150,
                        on_change=lambda e: setattr(self, 'v_spectral_mask_att', int(e.control.value))),
                ft.Text(f"{self.v_spectral_mask_att}", width=50),
                ft.Text("Пиков: ", width=60),
                ft.Slider(min=1, max=20, value=self.v_spectral_mask_peaks, width=150,
                        on_change=lambda e: setattr(self, 'v_spectral_mask_peaks', int(e.control.value))),
                ft.Text(f"{self.v_spectral_mask_peaks}", width=50),
            ])
        )
        
        concert_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="light", text="light"),
                ft.DropdownOption(key="medium", text="medium"),
                ft.DropdownOption(key="heavy", text="heavy"),
            ],
            value=self.v_concert_intensity,
            width=100,
            on_select=lambda e: setattr(self, 'v_concert_intensity', e.control.value or "medium")
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Эмуляция концертной записи", value=self.v_concert_emu,
                        on_change=lambda e: setattr(self, 'v_concert_emu', e.control.value)),
                concert_dropdown,
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Mid/Side обработка", value=self.v_midside,
                        on_change=lambda e: setattr(self, 'v_midside', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Mid Gain (dB): ", width=100),
                ft.Slider(min=-12, max=6, value=self.v_midside_mid, width=150,
                        on_change=lambda e: setattr(self, 'v_midside_mid', e.control.value)), 
                ft.Text(f"{self.v_midside_mid:.1f}", width=50),
                ft.Text("Side Gain (dB): ", width=100),
                ft.Slider(min=-6, max=12, value=self.v_midside_side, width=150,
                        on_change=lambda e: setattr(self, 'v_midside_side', e.control.value)),
                ft.Text(f"{self.v_midside_side:.1f}", width=50),
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Психоакустический шум", value=self.v_psycho_noise,
                        on_change=lambda e: setattr(self, 'v_psycho_noise', e.control.value)),
                ft.Slider(min=0.0001, max=0.01, value=self.v_psycho_intensity, width=200,
                        on_change=lambda e: setattr(self, 'v_psycho_intensity', e.control.value)),
                ft.Text(f"{self.v_psycho_intensity:.4f}", size=12),
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Аналоговое насыщение", value=self.v_saturation,
                        on_change=lambda e: setattr(self, 'v_saturation', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Drive: ", width=50),
                ft.Slider(min=1, max=5, value=self.v_saturation_drive, width=150,
                        on_change=lambda e: setattr(self, 'v_saturation_drive', e.control.value)),
                ft.Text(f"{self.v_saturation_drive:.1f}", width=50),
                ft.Text("Mix: ", width=50),
                ft.Slider(min=0, max=1, value=self.v_saturation_mix, width=150,
                        on_change=lambda e: setattr(self, 'v_saturation_mix', e.control.value)),
                ft.Text(f"{self.v_saturation_mix:.2f}", width=50),
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Временной джиттер", value=self.v_temp_jitter,
                        on_change=lambda e: setattr(self, 'v_temp_jitter', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Интенсивность: ", width=100),
                ft.Slider(min=0, max=0.01, value=self.v_jitter_intensity, width=150,
                        on_change=lambda e: setattr(self, 'v_jitter_intensity', e.control.value)),
                ft.Text(f"{self.v_jitter_intensity:.4f}", width=60),
                ft.Text("Частота (Гц): ", width=100),
                ft.Slider(min=0.1, max=10, value=self.v_jitter_freq, width=150,
                        on_change=lambda e: setattr(self, 'v_jitter_freq', e.control.value)),
                ft.Text(f"{self.v_jitter_freq:.1f}", width=50),
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Спектральный джиттер", value=self.v_spec_jitter,
                        on_change=lambda e: setattr(self, 'v_spec_jitter', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Кол-во провалов: ", width=110),
                ft.Slider(min=0.1, max=15, value=self.v_spec_jitter_count, width=150,
                        on_change=lambda e: setattr(self, 'v_spec_jitter_count', e.control.value)),
                ft.Text(f"{self.v_spec_jitter_count:.1f}", width=50),
                ft.Text("Аттенюация (dB): ", width=110),
                ft.Slider(min=0.1, max=30, value=self.v_spec_jitter_att, width=150,
                        on_change=lambda e: setattr(self, 'v_spec_jitter_att', e.control.value)),
                ft.Text(f"{self.v_spec_jitter_att:.1f}", width=50),
            ])
        )
        
        spec_jitter_mode_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="random", text="random"),
                ft.DropdownOption(key="fixed", text="fixed"),
                ft.DropdownOption(key="manual", text="manual"),
            ],
            value=self.v_spec_jitter_mode,
            width=100,
            on_select=lambda e: setattr(self, 'v_spec_jitter_mode', e.control.value or "random")
        )
        
        controls.append(
            ft.Row([
                ft.Text("Режим: ", width=50),
                spec_jitter_mode_dropdown,
                ft.Text("Частоты (через запятую): "),
                ft.TextField(value=self.v_spec_jitter_fixed_freqs, width=200,
                    on_change=lambda e: setattr(self, 'v_spec_jitter_fixed_freqs', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Частоты: ", width=60),
                ft.TextField(value=self.v_spec_jitter_manual_freqs, width=150,
                    on_change=lambda e: setattr(self, 'v_spec_jitter_manual_freqs', e.control.value)),
                ft.Text("Ослабления: ", width=80),
                ft.TextField(value=self.v_spec_jitter_manual_atts, width=120,
                    on_change=lambda e: setattr(self, 'v_spec_jitter_manual_atts', e.control.value)),
                ft.Text("Ширины: ", width=60),
                ft.TextField(value=self.v_spec_jitter_manual_widths, width=120,
                    on_change=lambda e: setattr(self, 'v_spec_jitter_manual_widths', e.control.value)),
                ft.Text("Ширина по умолч.: ", width=120),
                ft.Slider(min=0.01, max=2, value=self.v_spec_jitter_fixed_width, width=150,
                        on_change=lambda e: setattr(self, 'v_spec_jitter_fixed_width', e.control.value)),
                ft.Text(f"{self.v_spec_jitter_fixed_width:.2f}", width=50),
            ])
        )
        
        controls.append(ft.Divider())
        controls.append(
            ft.Row([
                ft.Checkbox(label="VK Инфразвук", value=self.v_vk_infra,
                        on_change=lambda e: setattr(self, 'v_vk_infra', e.control.value)),
            ])
        )
        
        vk_infra_mode_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="simple", text="simple"),
                ft.DropdownOption(key="modulated", text="modulated"),
                ft.DropdownOption(key="phase", text="phase"),
                ft.DropdownOption(key="harmonic", text="harmonic"),
                ft.DropdownOption(key="maximum", text="maximum"),
            ],
            value=self.v_vk_infra_mode,
            width=100,
            on_select=lambda e: setattr(self, 'v_vk_infra_mode', e.control.value or "modulated")
        )
        
        controls.append(
            ft.Row([
                ft.Text("Режим: ", width=50),
                vk_infra_mode_dropdown,
                ft.Text("Частота (Гц): ", width=100),
                ft.Slider(min=1, max=25, value=self.v_vk_infra_freq, width=150,
                        on_change=lambda e: setattr(self, 'v_vk_infra_freq', e.control.value)),
                ft.Text(f"{self.v_vk_infra_freq:.1f}", width=50),
                ft.Text("Амплитуда: ", width=80),
                ft.Slider(min=0, max=1, value=self.v_vk_infra_amplitude, width=150,
                        on_change=lambda e: setattr(self, 'v_vk_infra_amplitude', e.control.value)),
                ft.Text(f"{self.v_vk_infra_amplitude:.2f}", width=50),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Мод. частота: ", width=100),
                ft.Slider(min=0.01, max=1, value=self.v_vk_infra_mod_freq, width=150,
                        on_change=lambda e: setattr(self, 'v_vk_infra_mod_freq', e.control.value)),
                ft.Text(f"{self.v_vk_infra_mod_freq:.2f}", width=50),
                ft.Text("Глубина мод.: ", width=100),
                ft.Slider(min=0, max=1, value=self.v_vk_infra_mod_depth, width=150,
                        on_change=lambda e: setattr(self, 'v_vk_infra_mod_depth', e.control.value)),
                ft.Text(f"{self.v_vk_infra_mod_depth:.2f}", width=50),
                ft.Text("Фаза: ", width=50),
                ft.Slider(min=0, max=6.28, value=self.v_vk_infra_phase_shift, width=150,
                        on_change=lambda e: setattr(self, 'v_vk_infra_phase_shift', e.control.value)),
                ft.Text(f"{self.v_vk_infra_phase_shift:.2f}", width=50),
            ])
        )
        
        vk_infra_waveform_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="sine", text="sine"),
                ft.DropdownOption(key="triangle", text="triangle"),
                ft.DropdownOption(key="square", text="square"),
            ],
            value=self.v_vk_infra_waveform,
            width=100,
            on_select=lambda e: setattr(self, 'v_vk_infra_waveform', e.control.value or "sine")
        )
        
        controls.append(
            ft.Row([
                ft.Text("Форма волны: ", width=90),
                vk_infra_waveform_dropdown,
                ft.Checkbox(label="Адаптивная амплитуда", value=self.v_vk_infra_adaptive,
                        on_change=lambda e: setattr(self, 'v_vk_infra_adaptive', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Гармоники: ", width=80),
                ft.Text("H2: ", width=30),
                ft.Slider(min=0, max=0.5, value=self.v_vk_infra_h1, width=100,
                        on_change=lambda e: setattr(self, 'v_vk_infra_h1', e.control.value)),
                ft.Text(f"{self.v_vk_infra_h1:.2f}", width=40),
                ft.Text("H3: ", width=30),
                ft.Slider(min=0, max=0.5, value=self.v_vk_infra_h2, width=100,
                        on_change=lambda e: setattr(self, 'v_vk_infra_h2', e.control.value)),
                ft.Text(f"{self.v_vk_infra_h2:.2f}", width=40),
                ft.Text("H4: ", width=30),
                ft.Slider(min=0, max=0.5, value=self.v_vk_infra_h3, width=100,
                        on_change=lambda e: setattr(self, 'v_vk_infra_h3', e.control.value)),
                ft.Text(f"{self.v_vk_infra_h3:.2f}", width=40),
            ])
        )
        controls.append(ft.Text("Подмешивает инфразвуковую синусоиду с различными режимами модуляции.", size=11, italic=True, color=ft.Colors.GREY))
        
        return ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.AUTO), padding=10, height=600)

    def _build_advanced_tab(self):
        controls = []
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Вырезать фрагмент", value=self.v_cut,
                        on_change=lambda e: setattr(self, 'v_cut', e.control.value)),
            ])
        )
        controls.append(
            ft.Row([
                ft.Text("Позиция (%): ", width=100),
                ft.Slider(min=0, max=100, value=self.v_cut_pos, width=200,
                        on_change=lambda e: setattr(self, 'v_cut_pos', int(e.control.value))),
                ft.Text(f"{self.v_cut_pos}%", width=50),
                ft.Text("Длительность (сек): ", width=120),
                ft.Slider(min=0.1, max=30, value=self.v_cut_dur, width=200,
                        on_change=lambda e: setattr(self, 'v_cut_dur', e.control.value)),
                ft.Text(f"{self.v_cut_dur:.1f} сек", width=60),
            ])
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Сращивание треков", value=self.v_merge,
                        on_change=lambda e: setattr(self, 'v_merge', e.control.value)),
                ft.TextField(label="Дополнительный трек", value=self.v_extra, width=400,
                    on_change=lambda e: setattr(self, 'v_extra', e.control.value)),
                ft.FilledButton("Выбрать", on_click=lambda e: self._select_extra_track()),
            ])
        )
        
        broken_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="0", text="0: Случайная большая длительность"),
                ft.DropdownOption(key="1", text="1: Случайная малая длительность"),
                ft.DropdownOption(key="2", text="2: Случайная средняя длительность"),
                ft.DropdownOption(key="3", text="3: Максимальная длительность"),
            ],
            value=str(self.v_broken_t),
            width=300,
            on_select=lambda e: setattr(self, 'v_broken_t', int(e.control.value) if e.control.value.isdigit() else 0)
        )
        
        controls.append(
            ft.Row([
                ft.Checkbox(label="Подмена длительности", value=self.v_broken,
                        on_change=lambda e: setattr(self, 'v_broken', e.control.value)),
                broken_dropdown,
            ])
        )
        
        return ft.Container(content=ft.Column(controls, spacing=8), padding=10)

    def _build_metadata_tab(self):
        self.title_field = ft.TextField(label="Название", value=self.v_title, width=300,
            on_change=lambda e: setattr(self, 'v_title', e.control.value))
        self.artist_field = ft.TextField(label="Исполнитель", value=self.v_artist, width=300,
            on_change=lambda e: setattr(self, 'v_artist', e.control.value))
        self.album_field = ft.TextField(label="Альбом", value=self.v_album, width=300,
            on_change=lambda e: setattr(self, 'v_album', e.control.value))
        self.year_field = ft.TextField(label="Год", value=self.v_year, width=150,
            on_change=lambda e: setattr(self, 'v_year', e.control.value))
        self.genre_field = ft.TextField(label="Жанр", value=self.v_genre, width=200,
            on_change=lambda e: setattr(self, 'v_genre', e.control.value))
        
        controls = [
            self.title_field,
            self.artist_field,
            self.album_field,
            ft.Row([self.year_field, self.genre_field], spacing=20),
            ft.Row([
                ft.FilledButton("Копировать из оригинала", on_click=lambda e: self._copy_meta()),
                ft.FilledButton("Рандом", on_click=lambda e: self._random_meta()),
                ft.FilledButton("Очистить", on_click=lambda e: self._clear_meta()),
            ], spacing=10),
        ]
        
        return ft.Container(content=ft.Column(controls, spacing=10), padding=10)

    def _build_filename_tab(self):
        self.template_field = ft.TextField(
            label="Шаблон имени файла",
            value=self.v_filename_template,
            width=400,
            on_change=lambda e: setattr(self, 'v_filename_template', e.control.value)
        )
        
        self.template_list = ft.ListView(height=150, spacing=2)
        self._refresh_template_list()
        
        self.new_template_name = ft.TextField(label="Название шаблона", width=200)
        self.template_pattern = ft.TextField(label="Шаблон", value="", width=400, multiline=True)
        
        variables = [
            ft.FilledButton("{n}", on_click=lambda e: self._insert_template_var("{n}")),
            ft.FilledButton("{n:03d}", on_click=lambda e: self._insert_template_var("{n:03d}")),
            ft.FilledButton("{original}", on_click=lambda e: self._insert_template_var("{original}")),
            ft.FilledButton("{title}", on_click=lambda e: self._insert_template_var("{title}")),
            ft.FilledButton("{artist}", on_click=lambda e: self._insert_template_var("{artist}")),
            ft.FilledButton("{album}", on_click=lambda e: self._insert_template_var("{album}")),
            ft.FilledButton("{year}", on_click=lambda e: self._insert_template_var("{year}")),
        ]
        
        preview_label = ft.Text("Предпросмотр: --", italic=True)
        self.filename_preview = preview_label
        
        controls = [
            self.template_field,
            ft.Divider(),
            ft.Text("Сохранённые шаблоны:", weight=ft.FontWeight.BOLD),
            self.template_list,
            ft.Row([
                ft.FilledButton("Загрузить", on_click=lambda e: self._load_selected_template()),
                ft.FilledButton("Удалить", on_click=lambda e: self._delete_selected_template()),
            ], spacing=10),
            ft.Divider(),
            ft.Text("Конструктор шаблона:", weight=ft.FontWeight.BOLD),
            self.new_template_name,
            self.template_pattern,
            ft.Text("Быстрая вставка:", size=12),
            ft.Row(variables, wrap=True, spacing=5),
            ft.Row([
                ft.FilledButton("Сохранить шаблон", on_click=lambda e: self._save_template()),
            ], spacing=10),
            preview_label,
        ]
        
        return ft.Container(content=ft.Column(controls, spacing=10), padding=10)

    def _build_technical_tab(self):
        controls = [
            ft.Checkbox(label="Рандомизация битрейта", value=self.v_bitrate_j,
                       on_change=lambda e: setattr(self, 'v_bitrate_j', e.control.value)),
            ft.Text("Случайно выбирает битрейт из {192, 224, 256, 320} kbps.", size=11, italic=True, color=ft.Colors.GREY),
            ft.Checkbox(label="Удаление заголовка Xing", value=self.v_frame_sh,
                       on_change=lambda e: setattr(self, 'v_frame_sh', e.control.value)),
            ft.Text("Удаляет Xing/VBR заголовок, делая файл похожим на CBR.", size=11, italic=True, color=ft.Colors.GREY),
            ft.Checkbox(label="Мусор в поле comment", value=self.v_fake_meta,
                       on_change=lambda e: setattr(self, 'v_fake_meta', e.control.value)),
            ft.Text("Добавляет случайную строку в поле comment для сбивания анализа.", size=11, italic=True, color=ft.Colors.GREY),
            ft.Checkbox(label="Переупорядочить ID3 теги", value=self.v_reorder,
                       on_change=lambda e: setattr(self, 'v_reorder', e.control.value)),
            ft.Text("Перезаписывает ID3v2 теги в порядке v2.3 стандарта.", size=11, italic=True, color=ft.Colors.GREY),
        ]
        return ft.Container(content=ft.Column(controls, spacing=8), padding=10)

    def _build_system_tab(self):
        cpu_count = os.cpu_count() or 4
        
        controls = [
            ft.Text("Параллельных потоков:", weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Slider(min=1, max=min(16, cpu_count * 2), value=self.v_max_workers, width=300,
                         on_change=lambda e: setattr(self, 'v_max_workers', int(e.control.value))),
                ft.Text(f"{self.v_max_workers}", width=40),
                ft.FilledButton(f"Авто ({cpu_count})", on_click=lambda e: setattr(self, 'v_max_workers', cpu_count)),
            ]),
            ft.Text("Количество одновременно обрабатываемых файлов. Рекомендуется = числу ядер CPU.", size=11, italic=True, color=ft.Colors.GREY),
            ft.Text("Задержка между запусками (сек):", weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Slider(min=0, max=5, value=self.v_thread_delay, width=300,
                         on_change=lambda e: setattr(self, 'v_thread_delay', e.control.value)),
                ft.Text(f"{self.v_thread_delay:.1f}", width=40),
            ]),
            ft.Text("Задержка перед запуском обработки каждого файла (полезно при пакетной обработке).", size=11, italic=True, color=ft.Colors.GREY),
            ft.Divider(),
            ft.Text(f"Drag & Drop: доступен (Flet)", size=12),
            ft.Text("Горячие клавиши: Ctrl+O, Ctrl+A, Delete, Ctrl+S", size=11, color=ft.Colors.GREY),
        ]
        return ft.Container(content=ft.Column(controls, spacing=8), padding=10)

    def _build_output_section(self):
        self.lbl_out_dir = ft.Text(self.output_dir)
        
        quality_dropdown = ft.Dropdown(
            options=[
                ft.DropdownOption(key="320 kbps (CBR)", text="320 kbps (CBR)"),
                ft.DropdownOption(key="245 kbps (VBR Q0)", text="245 kbps (VBR Q0)"),
                ft.DropdownOption(key="175 kbps (VBR Q4)", text="175 kbps (VBR Q4)"),
                ft.DropdownOption(key="130 kbps (VBR Q6)", text="130 kbps (VBR Q6)"),
            ],
            value=self.v_quality,
            width=200,
            on_select=lambda e: setattr(self, 'v_quality', e.control.value or "320 kbps (CBR)")
        )
        
        controls = ft.Column([
            ft.Row([
                ft.FilledButton("Выбрать папку", on_click=lambda e: self._select_output_dir()),
                self.lbl_out_dir,
            ]),
            ft.Checkbox(label="Сохранить оригинальные теги", value=self.v_preserve_meta,
                    on_change=lambda e: setattr(self, 'v_preserve_meta', e.control.value)),
            ft.Checkbox(label="Сохранить оригинальную обложку", value=self.v_preserve_cover,
                    on_change=lambda e: setattr(self, 'v_preserve_cover', e.control.value)),
            ft.Checkbox(label="Удалять оригиналы после обработки", value=self.v_delete_orig,
                    on_change=lambda e: setattr(self, 'v_delete_orig', e.control.value)),
            ft.Row([
                ft.Text("Качество аудио: ", weight=ft.FontWeight.BOLD),
                quality_dropdown,
            ]),
            ft.Text("320 kbps — макс. качество | 130 kbps — мин. размер", size=11, color=ft.Colors.GREY),
        ], spacing=8)
        
        return ft.Container(
            content=controls, 
            padding=10, 
            border=ft.Border(
                top=ft.BorderSide(1, ft.Colors.OUTLINE),
                bottom=ft.BorderSide(1, ft.Colors.OUTLINE),
                left=ft.BorderSide(1, ft.Colors.OUTLINE),
                right=ft.BorderSide(1, ft.Colors.OUTLINE)
            ),
            border_radius=10
        )

    def _build_action_section(self):
        self.progress_bar = ft.ProgressBar(width=400)
        self.btn_start = ft.FilledButton("Запустить обработку", on_click=lambda e: self._start())
        
        return ft.Container(
            content=ft.Row([self.progress_bar, self.btn_start], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=10
        )

    def _build_log_section(self):
        self.log_text = ft.TextField(
            multiline=True,
            read_only=True,
            min_lines=8,
            max_lines=8,
            value="",
        )
        return ft.Container(content=ft.Column([ft.Text("Лог", weight=ft.FontWeight.BOLD), self.log_text]), padding=10)

    def _build_converter_interface(self):
        self.cmb_conv_format = ft.Dropdown(
            options=[ft.DropdownOption(key=fmt, text=fmt) for fmt in SUPPORTED_FORMATS.keys()],
            value=self.v_conv_format,
            width=120,
            on_select=lambda e: self._on_format_changed(e.control.value)
        )
        
        self.cmb_conv_quality = ft.Dropdown(width=200)
        self.lbl_format_desc = ft.Text("", size=11, color=ft.Colors.GREY)
        self.lbl_out_dir_conv = ft.Text(self.output_dir)
        
        self.conv_progress_bar = ft.ProgressBar(width=400)
        self.btn_convert = ft.FilledButton("Запустить конвертацию", on_click=lambda e: self._start_conversion())
        
        self.conv_log_text = ft.TextField(multiline=True, read_only=True, min_lines=8, max_lines=8, value="")
        
        self._on_format_changed(self.v_conv_format)
        
        controls = ft.Column([
            ft.Row([
                ft.Text("Конвертер аудиоформатов", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Поддерживается 26 форматов", size=12, color=ft.Colors.GREY),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.Text("Настройки конвертации", weight=ft.FontWeight.BOLD),
            ft.Row([ft.Text("Выходной формат: "), self.cmb_conv_format, self.lbl_format_desc]),
            ft.Row([ft.Text("Качество: "), self.cmb_conv_quality]),
            ft.Text("Настройки вывода", weight=ft.FontWeight.BOLD),
            ft.Row([ft.FilledButton("Выбрать папку", on_click=lambda e: self._select_output_dir()), self.lbl_out_dir_conv]),
            ft.Checkbox(label="Удалять оригиналы после конвертации", value=self.v_conv_delete,
                    on_change=lambda e: setattr(self, 'v_conv_delete', e.control.value)),
            ft.Text("Поддерживаемые форматы", weight=ft.FontWeight.BOLD),
            ft.Text(
                "Lossy: MP3, AAC/M4A, OGG, Opus, WMA, AC3, DTS, MP2, MPC, Speex, AMR\n "
                "Lossless: FLAC, WAV, AIFF, ALAC, WV, APE, TTA, SHN, OGG FLAC\n "
                "Другие: MKA, CAF, AU ",
                size=11, selectable=True
            ),
            ft.Row([self.conv_progress_bar, self.btn_convert], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text("Лог конвертации", weight=ft.FontWeight.BOLD),
            self.conv_log_text,
        ], spacing=10)
        
        return ft.Container(content=controls, padding=10, expand=True)

    def _on_format_changed(self, fmt):
        desc = SUPPORTED_FORMATS.get(fmt, '')
        self.lbl_format_desc.value = desc
        
        if fmt in QUALITY_PRESETS:
            self.cmb_conv_quality.options = [ft.DropdownOption(key=q, text=q) for q in QUALITY_PRESETS[fmt]]
            self.cmb_conv_quality.value = QUALITY_PRESETS[fmt][0] if QUALITY_PRESETS[fmt] else ''
            self.cmb_conv_quality.disabled = False
        elif fmt in ['wav', 'aiff', 'au', 'caf']:
            self.cmb_conv_quality.options = [ft.DropdownOption(key='Uncompressed PCM', text='Uncompressed PCM')]
            self.cmb_conv_quality.value = 'Uncompressed PCM' 
            self.cmb_conv_quality.disabled = True
        elif fmt == 'flac':
            opts = ['Compression 0 (fast)', 'Compression 5 (default)', 'Compression 8 (best)', 'Compression 12 (max)']
            self.cmb_conv_quality.options = [ft.DropdownOption(key=o, text=o) for o in opts]
            self.cmb_conv_quality.value = 'Compression 5 (default)'
            self.cmb_conv_quality.disabled = False
        elif fmt in ['alac', 'wv', 'ape', 'tta', 'shn']:
            self.cmb_conv_quality.options = [ft.DropdownOption(key='Lossless / Default', text='Lossless / Default')]
            self.cmb_conv_quality.value = 'Lossless / Default'
            self.cmb_conv_quality.disabled = True
        else:
            self.cmb_conv_quality.options = [ft.DropdownOption(key='Default quality', text='Default quality')]
            self.cmb_conv_quality.value = 'Default quality'
            self.cmb_conv_quality.disabled = True
        
        self.page.update()

    def _insert_template_var(self, var):
        self.template_pattern.value += var
        self._update_template_preview()
        self.page.update()

    def _refresh_template_list(self):
        self.template_list.controls.clear()
        for tpl in self.user_templates:
            self.template_list.controls.append(
                ft.Container(
                    content=ft.Text(f"{tpl['name']}  ->  {tpl['pattern']}"),
                    padding=5,
                    on_click=lambda e, t=tpl: self._on_template_click(t)
                )
            )

    def _on_template_click(self, template):
        self.template_pattern.value = template['pattern']
        self.new_template_name.value = template['name']
        self._update_template_preview()
        self.page.update()

    def _load_selected_template(self):
        if self.new_template_name.value:
            for tpl in self.user_templates:
                if tpl['name'] == self.new_template_name.value:
                    self.template_field.value = tpl['pattern']
                    self.v_filename_template = tpl['pattern']
                    self._update_filename_preview()
                    self._save_config()
                    self._log(f"Шаблон '{tpl['name']}' загружен", 'success')
                    break

    def _delete_selected_template(self):
        if self.new_template_name.value:
            for i, tpl in enumerate(self.user_templates):
                if tpl['name'] == self.new_template_name.value:
                    self.user_templates.pop(i)
                    self._refresh_template_list()
                    self._save_config()
                    self._log(f"Шаблон '{tpl['name']}' удалён", 'warning')
                    break

    def _save_template(self):
        name = self.new_template_name.value.strip()
        pattern = self.template_pattern.value.strip()
        
        if not name:
            self._log("Введите название шаблона", 'error')
            return
        if not pattern:
            self._log("Введите шаблон", 'error')
            return
        
        try:
            pattern.format(n=1, original='test', title='test', artist='test', album='test', year='2024')
        except (KeyError, ValueError) as e:
            self._log(f"Некорректный шаблон: {e}", 'error')
            return
        
        for i, tpl in enumerate(self.user_templates):
            if tpl['name'] == name:
                self.user_templates[i]['pattern'] = pattern
                self._refresh_template_list()
                self._save_config()
                self._log(f"Шаблон '{name}' обновлён", 'success')
                return
        
        self.user_templates.append({'name': name, 'pattern': pattern})
        self._refresh_template_list()
        self._save_config()
        self._log(f"Шаблон '{name}' сохранён", 'success')

    def _update_template_preview(self):
        tpl = self.template_pattern.value
        if not tpl:
            self.filename_preview.value = "Предпросмотр: --"
            return
        
        try:
            fname = tpl.format(
                n=1,
                original='example_track',
                title='Example Song',
                artist='Example Artist',
                album='Example Album',
                year='2024'
            ) + '.mp3'
            self.filename_preview.value = f"Предпросмотр: {fname}"
        except (KeyError, ValueError) as e:
            self.filename_preview.value = f"Ошибка: {e}"

    def _update_filename_preview(self):
        tpl = self.v_filename_template
        if not tpl:
            return
        
        if self.current_index >= 0 and self.current_index < len(self.tracks_info):
            ti = self.tracks_info[self.current_index]
            orig = os.path.splitext(os.path.basename(self.input_files[self.current_index]))[0]
            ex_title = self.v_title or ti.title or orig
            ex_artist = self.v_artist or ti.artist or ''
            ex_album = self.v_album or ti.album or ''
            ex_year = self.v_year or ti.year or ''
            n_val = self.current_index + 1
        else:
            orig = 'example_track'
            ex_title = 'Example Song'
            ex_artist = 'Example Artist'
            ex_album = 'Example Album'
            ex_year = '2024'
            n_val = 1
        
        try:
            fname = tpl.format(
                n=n_val,
                original=self._safe_filename(orig),
                title=self._safe_filename(ex_title),
                artist=self._safe_filename(ex_artist),
                album=self._safe_filename(ex_album),
                year=self._safe_filename(str(ex_year))
            ) + '.mp3'
            if hasattr(self, 'filename_preview'):
                self.filename_preview.value = f"Предпросмотр: {fname}"
        except (KeyError, ValueError) as e:
            if hasattr(self, 'filename_preview'):
                self.filename_preview.value = f"Ошибка: {e}"

    def _copy_meta(self):
        if self.current_index < 0:
            self._log("Сначала выберите файл", 'warning')
            return
        t = self.tracks_info[self.current_index]
        if t:
            self.v_title = t.title
            self.v_artist = t.artist
            self.v_album = t.album
            self.v_year = t.year
            self.v_genre = t.genre
            if hasattr(self, 'title_field'):
                self.title_field.value = t.title
                self.artist_field.value = t.artist
                self.album_field.value = t.album
                self.year_field.value = t.year
                self.genre_field.value = t.genre
            self._log("Метаданные скопированы из оригинала", 'success')
            self.page.update()

    def _random_meta(self):
        self.v_title = f"Track {random.randint(1, 999)}"
        self.v_artist = f"Artist {random.randint(1, 99)}"
        self.v_album = f"Album {random.randint(2000, 2025)}"
        self.v_year = str(random.randint(2000, 2025))
        self.v_genre = random.choice(["Pop", "Rock", "Electronic", "Hip Hop"])
        if hasattr(self, 'title_field'):
            self.title_field.value = self.v_title
            self.artist_field.value = self.v_artist
            self.album_field.value = self.v_album
            self.year_field.value = self.v_year
            self.genre_field.value = self.v_genre
        self._log("Случайные метаданные", 'success')
        self.page.update()

    def _clear_meta(self):
        self.v_title = ""
        self.v_artist = ""
        self.v_album = ""
        self.v_year = ""
        self.v_genre = ""
        if hasattr(self, 'title_field'):
            self.title_field.value = ""
            self.artist_field.value = ""
            self.album_field.value = ""
            self.year_field.value = ""
            self.genre_field.value = ""
        self.page.update()

    def _select_output_dir(self):
        def on_result(e: ft.FilePickerResultEvent):
            if e.path:
                self.output_dir = e.path
                self.lbl_out_dir.value = e.path
                if hasattr(self, 'lbl_out_dir_conv'):
                    self.lbl_out_dir_conv.value = e.path
                self._save_config()
                self._log(f"Папка вывода: {e.path}", 'success')
                self.page.update()
        
        file_picker = ft.FilePicker(on_result=on_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        file_picker.get_directory_path()

    def _select_extra_track(self):
        def on_result(e: ft.FilePickerResultEvent):
            if e.files:
                self.v_extra = e.files[0].path
                self._log(f"Выбран дополнительный трек: {os.path.basename(self.v_extra)}", 'success')
        
        file_picker = ft.FilePicker(on_result=on_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.AUDIO)

    def _add_files_dialog(self):
        def on_result(e: ft.FilePickerResultEvent):
            if e.files:
                files = [f.path for f in e.files]
                self._add_files(files)
        
        file_picker = ft.FilePicker(on_result=on_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        if self._mode == 'converter':
            file_picker.pick_files(allow_multiple=True, allowed_extensions=list(SUPPORTED_FORMATS.keys()))
        else:
            file_picker.pick_files(allow_multiple=True, allowed_extensions=['mp3'])

    def _add_files(self, files):
        added = 0
        for fp in files:
            if fp not in self.input_files:
                self.input_files.append(fp)
                if self._mode == 'modifier':
                    self.tracks_info.append(TrackInfo(fp))
                else:
                    self.tracks_info.append(None)
                self.file_listbox.controls.append(
                    ft.Container(content=ft.Text(os.path.basename(fp)), padding=5)
                )
                added += 1
        if added:
            self._update_stats()
            self._log(f"Добавлено файлов: {added}", 'success')
            self.page.update()

    def _clear_files(self):
        self.input_files.clear()
        self.tracks_info.clear()
        self.file_listbox.controls.clear()
        self.current_index = -1
        self._update_stats()
        self._log("Список очищен", 'warning')
        self.page.update()

    def _remove_selected(self):
        if self.current_index < 0:
            return
        name = os.path.basename(self.input_files[self.current_index])
        self.input_files.pop(self.current_index)
        self.tracks_info.pop(self.current_index)
        self.file_listbox.controls.pop(self.current_index)
        self.current_index = -1
        self._update_stats()
        self._log(f"Удалён: {name}", 'warning')
        self.page.update()

    def _update_stats(self):
        n = len(self.input_files)
        total_mb = sum(os.path.getsize(f) for f in self.input_files) / (1024 * 1024) if self.input_files else 0
        self.lbl_stats.value = f"{n} файлов | {total_mb:.1f} MB"
        self.page.update()

    def _collect_settings(self):
        quality_map = ['320k', '0', '4', '6']
        q_idx = 0
        try:
            q_vals = ['320 kbps (CBR)', '245 kbps (VBR Q0)', '175 kbps (VBR Q4)', '130 kbps (VBR Q6)']
            q_idx = q_vals.index(self.v_quality)
        except ValueError:
            pass
        
        return {
            'methods': {
                'pitch': self.v_pitch, 'speed': self.v_speed, 'eq': self.v_eq,
                'silence': self.v_silence, 'phase_invert': self.v_phase_inv,
                'phase_scramble': self.v_phase_scr, 'dc_shift': self.v_dc,
                'resample_drift': self.v_resamp, 'ultrasonic_noise': self.v_ultra,
                'haas_delay': self.v_haas, 'dither_attack': self.v_dither,
                'id3_padding_attack': self.v_id3pad, 'trim_silence': self.v_trim,
                'cut_fragment': self.v_cut, 'fade_out': self.v_fade, 'merge': self.v_merge,
                'broken_duration': self.v_broken, 'bitrate_jitter': self.v_bitrate_j,
                'frame_shift': self.v_frame_sh, 'fake_metadata': self.v_fake_meta,
                'reorder_tags': self.v_reorder, 'spectral_masking': self.v_spectral_mask,
                'concert_emulation': self.v_concert_emu, 'midside_processing': self.v_midside,
                'psychoacoustic_noise': self.v_psycho_noise, 'saturation': self.v_saturation,
                'temporal_jitter': self.v_temp_jitter, 'spectral_jitter': self.v_spec_jitter,
                'vk_infrasonic': self.v_vk_infra
            },
            'pitch_value': self.v_pitch_val,
            'speed_value': self.v_speed_val,
            'eq_type': self.v_eq_type,
            'eq_value': self.v_eq_val,
            'silence_duration': self.v_silence_val,
            'phase_invert_strength': self.v_phase_inv_val,
            'phase_scramble_speed': self.v_phase_scr_val,
            'dc_shift_value': self.v_dc_val,
            'resample_drift_amount': self.v_resamp_val,
            'ultrasonic_freq': self.v_ultra_freq,
            'ultrasonic_level': self.v_ultra_level,
            'haas_delay_ms': self.v_haas_val,
            'dither_method': self.v_dither_method,
            'id3_padding_bytes': self.v_id3pad_val,
            'trim_duration': self.v_trim_val,
            'cut_position_percent': self.v_cut_pos,
            'cut_duration': self.v_cut_dur,
            'fade_duration': self.v_fade_val,
            'extra_track_path': self.v_extra,
            'broken_type': self.v_broken_t,
            'quality': quality_map[q_idx],
            'filename_template': self.v_filename_template,
            'rename_files': self.v_rename,
            'preserve_metadata': self.v_preserve_meta,
            'preserve_cover': self.v_preserve_cover,
            'delete_original': self.v_delete_orig,
            'selected_cover_path': self.selected_cover_path,
            'spectral_mask_sensitivity': self.v_spectral_mask_sens,
            'spectral_mask_attenuation': self.v_spectral_mask_att,
            'spectral_mask_peaks': self.v_spectral_mask_peaks,
            'concert_intensity': self.v_concert_intensity,
            'midside_mid_gain': self.v_midside_mid,
            'midside_side_gain': self.v_midside_side,
            'psychoacoustic_intensity': self.v_psycho_intensity,
            'saturation_drive': self.v_saturation_drive,
            'saturation_mix': self.v_saturation_mix,
            'jitter_intensity': self.v_jitter_intensity,
            'jitter_frequency': self.v_jitter_freq,
            'spectral_jitter_count': self.v_spec_jitter_count,
            'spectral_jitter_attenuation': self.v_spec_jitter_att,
            'spectral_jitter_mode': self.v_spec_jitter_mode,
            'spectral_jitter_fixed_frequencies': [float(f.strip()) for f in self.v_spec_jitter_fixed_freqs.split(',') if f.strip()],
            'spectral_jitter_fixed_attenuation': self.v_spec_jitter_att,
            'spectral_jitter_manual_config': {
                'mode': self.v_spec_jitter_mode,
                'frequencies': [float(f.strip()) for f in self.v_spec_jitter_manual_freqs.split(',') if f.strip()],
                'attenuations': [float(a.strip()) for a in self.v_spec_jitter_manual_atts.split(',') if a.strip()],
                'widths': [float(w.strip()) for w in self.v_spec_jitter_manual_widths.split(',') if w.strip()],
                'fixed_width': self.v_spec_jitter_fixed_width
            },
            'vk_infrasonic_freq': self.v_vk_infra_freq,
            'vk_infrasonic_amplitude': self.v_vk_infra_amplitude,
            'vk_infrasonic_mode': self.v_vk_infra_mode,
            'vk_infrasonic_mod_freq': self.v_vk_infra_mod_freq,
            'vk_infrasonic_mod_depth': self.v_vk_infra_mod_depth,
            'vk_infrasonic_phase_shift': self.v_vk_infra_phase_shift,
            'vk_infrasonic_waveform': self.v_vk_infra_waveform,
            'vk_infrasonic_adaptive_amplitude': self.v_vk_infra_adaptive,
            'vk_infrasonic_harmonics': [self.v_vk_infra_h1, self.v_vk_infra_h2, self.v_vk_infra_h3],
        }

    def _start(self):
        if not self.input_files:
            self._log("Добавьте MP3 файлы", 'warning')
            return
        if not self.output_dir:
            self._log("Выберите папку для сохранения", 'warning')
            return
        if not self.ffmpeg_ok:
            self._log("FFmpeg не найден!", 'error')
            return
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.btn_start.disabled = True
        self.progress_bar.value = 0
        self._completed_count = 0
        
        settings = self._collect_settings()
        metadata = {
            'title': self.v_title, 'artist': self.v_artist,
            'album': self.v_album, 'year': self.v_year, 'genre': self.v_genre
        }
        
        self._log(f"Запущена обработка ({self.v_max_workers} поток(а))...", 'info')
        
        from core_logic import ModificationWorker
        worker = ModificationWorker(
            files=list(self.input_files), tracks_info=list(self.tracks_info),
            output_dir=self.output_dir, settings=settings, metadata=metadata,
            on_progress=lambda cur, tot, fp: self._worker_queue.put(('progress', cur, tot, fp)),
            on_file_complete=lambda fp, ok, out: self._worker_queue.put(('file_done', fp, ok, out)),
            on_all_complete=lambda sc, tot: self._worker_queue.put(('all_done', sc, tot)),
            on_error=lambda msg: self._worker_queue.put(('error', msg))
        )
        worker.start()

    def _start_conversion(self):
        if not self.input_files:
            self._log("Добавьте аудиофайлы для конвертации", 'warning', True)
            return
        if not self.output_dir:
            self._log("Выберите папку для сохранения", 'warning', True)
            return
        if not self.ffmpeg_ok:
            self._log("FFmpeg не найден!", 'error', True)
            return
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.btn_convert.disabled = True
        self.conv_progress_bar.value = 0
        self._completed_count = 0
        
        self._log(f"Запущена конвертация {len(self.input_files)} файлов в {self.v_conv_format.upper()}...", 'info', True)
        
        converter = BatchConverter(
            files=list(self.input_files), output_dir=self.output_dir,
            output_format=self.v_conv_format, quality_preset=self.v_conv_quality,
            result_queue=self._worker_queue, max_workers=self.v_max_workers,
            delete_originals=self.v_conv_delete
        )
        converter.run_in_thread()

    def _start_queue_polling(self):
        async def poll():
            while True:
                try:
                    while True:
                        msg = self._worker_queue.get_nowait()
                        kind = msg[0]
                        
                        if kind == 'progress':
                            _, cur, tot, fp = msg
                            if self._mode == 'converter':
                                self._log(f"[{cur}/{tot}] {os.path.basename(fp)}", 'info', True)
                            else:
                                self._log(f"[{cur}/{tot}] {os.path.basename(fp)}", 'info')
                        elif kind == 'file_done':
                            _, fp, ok, out = msg
                            self._completed_count += 1
                            if self._mode == 'converter':
                                self.conv_progress_bar.value = self._completed_count / len(self.input_files) if self.input_files else 0
                                if ok:
                                    self._log(f"OK {os.path.basename(fp)} -> {os.path.basename(out)}", 'success', True)
                                else:
                                    self._log(f"ERROR {os.path.basename(fp)}", 'error', True)
                            else:
                                self.progress_bar.value = self._completed_count / len(self.input_files) if self.input_files else 0
                                if ok:
                                    self._log(f"OK {os.path.basename(fp)} -> {os.path.basename(out)}", 'success')
                                else:
                                    self._log(f"ERROR {os.path.basename(fp)}", 'error')
                        elif kind == 'all_done':
                            _, sc, tot = msg
                            if self._mode == 'converter':
                                self.btn_convert.disabled = False
                                self._log(f"Конвертация завершена: {sc}/{tot} файлов", 'success', True)
                            else:
                                self.btn_start.disabled = False
                                self._log(f"Готово: {sc}/{tot} файлов обработано", 'success')
                        elif kind == 'error':
                            if self._mode == 'converter':
                                self._log(f"ERROR: {msg[1]}", 'error', True)
                            else:
                                self._log(f"ERROR: {msg[1]}", 'error')
                except queue.Empty:
                    pass
                self.page.update()
                await asyncio.sleep(0.1)
        
        asyncio.create_task(poll())

def main(page: ft.Page):
    app = VKModifierApp(page)


if __name__ == '__main__':
    ft.run(main)  # ← ПРАВИЛЬНО