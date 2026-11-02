import yt_dlp
import threading
import re
import os
import ssl
import sys
import base64
import contextlib
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_combined_certs(context, use_certifi=True):
    """Загрузить в SSL-контекст И certifi, И системные сертификаты."""
    # 1. certifi
    with contextlib.suppress(Exception):
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    # 2. Системные пути
    with contextlib.suppress(Exception):
        context.load_default_certs()
    # 3. Хранилище Windows (Root & CA)
    if sys.platform == 'win32' and hasattr(ssl, 'enum_certificates'):
        for storename in ('CA', 'ROOT'):
            with contextlib.suppress(Exception):
                certs = [
                    cert for cert, encoding, trust in ssl.enum_certificates(storename)
                    if encoding == 'x509_asn' and (
                        trust is True or ssl.Purpose.SERVER_AUTH.oid in trust)
                ]
            for cert in certs:
                pem = (
                    '-----BEGIN CERTIFICATE-----\n'
                    + base64.encodebytes(cert).decode('ascii')
                    + '-----END CERTIFICATE-----\n'
                )
                with contextlib.suppress(Exception):
                    context.load_verify_locations(cadata=pem)
    # 4. Явный бандл из окружения
    env_bundle = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
    if env_bundle and os.path.isfile(env_bundle):
        with contextlib.suppress(Exception):
            context.load_verify_locations(cafile=env_bundle)


def _install_combined_certs():
    """Подменить загрузку сертификатов yt-dlp на объединённую."""
    with contextlib.suppress(Exception):
        from yt_dlp.networking import _helper
        _helper.ssl_load_certs = _load_combined_certs


_install_combined_certs()


def _get_js_runtimes_config():
    """Сконфигурировать поддержку JS-рантаймов (Node, Deno, QuickJS, Bun) для yt-dlp."""
    runtimes = {'node': {}, 'deno': {}, 'quickjs': {}, 'bun': {}}
    
    node_candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "node.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "nodejs", "node.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "node", "node.exe"),
        os.path.join(BASE_DIR, "node.exe"),
    ]
    for p in node_candidates:
        if os.path.isfile(p):
            runtimes['node'] = {'path': p}
            break

    deno_path = os.path.join(BASE_DIR, "deno.exe")
    if os.path.isfile(deno_path):
        runtimes['deno'] = {'path': deno_path}

    qjs_path = os.path.join(BASE_DIR, "qjs.exe")
    if os.path.isfile(qjs_path):
        runtimes['quickjs'] = {'path': qjs_path}

    return runtimes


def detect_platform(url: str) -> str:
    """Определить платформу по ссылке."""
    url_lower = url.lower().strip()
    if "vk.com" in url_lower or "vkvideo.ru" in url_lower:
        return "VK"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "theasmrindex.com" in url_lower:
        return "TheASMRIndex"
    if "qqasmr.com" in url_lower:
        return "QQASMR"
    return "Другое"


def sanitize_filename(name: str) -> str:
    """Удалить запрещенные в Windows символы из имени файла."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:200] if clean else "video"


def extract_qqasmr_info(url: str, browser: str = ""):
    """Извлечь данные видео с QQASMR через сессионные cookies браузера."""
    m = re.search(r'qqasmr\.com/(?:[a-zA-Z\-]+/)?video/(\d+)', url)
    if not m:
        return False, "Неверный формат ссылки QQASMR. Ожидается вид: https://qqasmr.com/video/ID"
    video_id = m.group(1)
    page_url = f"https://qqasmr.com/video/{video_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    if browser and browser != "Нет":
        try:
            jar = yt_dlp.cookies.extract_cookies_from_browser(browser.lower())
            cookie_parts = [f"{c.name}={c.value}" for c in jar if 'qqasmr' in c.domain]
            if cookie_parts:
                headers['Cookie'] = "; ".join(cookie_parts)
        except Exception as e:
            return False, f"Ошибка чтения cookies из браузера {browser}: {e}"
            
    try:
        req = urllib.request.Request(page_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return False, f"Ошибка загрузки страницы QQASMR: {e}"
        
    flight = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', html)
    full_flight = "".join(f.encode().decode('unicode_escape', errors='ignore') for f in flight)
    
    title_match = re.search(r'<title>(.*?)(?:\s*\|\s*QQASMR)?</title>', html)
    title = title_match.group(1).strip() if title_match else f"QQASMR_{video_id}"
    title = sanitize_filename(title)
    
    video_match = re.search(r'"videoUrl":"(https?://[^"]+)"', full_flight)
    audio_match = re.search(r'"audioUrl":"(https?://[^"]+)"', full_flight)
    poster_match = re.search(r'"poster":"(https?://[^"]+)"', full_flight)
    
    if not video_match:
        if 'isLogin":false' in full_flight or 'LoginDialogTrigger' in full_flight:
            return False, (
                "Для просмотра и скачивания этого видео с QQASMR требуется вход в аккаунт.\n"
                "💡 Выберите в поле 'Cookies из браузера' браузер (например, Firefox или Chrome), "
                "в котором вы авторизованы на сайте qqasmr.com."
            )
        if 'isPremium":false' in full_flight:
            return False, "Видео на QQASMR доступно только пользователям с активной подпиской Premium."
        return False, "Не удалось обнаружить поток воспроизведения QQASMR."
        
    video_url = video_match.group(1).replace(r'\/', '/')
    audio_url = audio_match.group(1).replace(r'\/', '/') if audio_match else None
    poster_url = poster_match.group(1).replace(r'\/', '/') if poster_match else None
    
    return True, {
        'id': video_id,
        'title': title,
        'video_url': video_url,
        'audio_url': audio_url,
        'poster_url': poster_url,
        'original_url': url
    }


def normalize_url(url: str) -> tuple[str, str]:
    """Нормализовать ссылки специальных каталогов (например, theasmrindex.com).

    Возвращает: (normalized_url, note_message)
    """
    clean_url = url.strip()
    # TheASMRIndex -> YouTube или Twitch
    if "theasmrindex.com" in clean_url.lower():
        # video: https://www.theasmrindex.com/video/<id>
        m_vid = re.search(r'theasmrindex\.com/video/([a-zA-Z0-9_\-]+)', clean_url)
        if m_vid:
            yt_id = m_vid.group(1)
            return f"https://www.youtube.com/watch?v={yt_id}", f"TheASMRIndex → YouTube ({yt_id})"
        # channel: https://www.theasmrindex.com/channel/(UC[a-zA-Z0-9_\-]+)
        m_chan = re.search(r'theasmrindex\.com/channel/(UC[a-zA-Z0-9_\-]+)', clean_url)
        if m_chan:
            ch_id = m_chan.group(1)
            return f"https://www.youtube.com/channel/{ch_id}", f"TheASMRIndex → Канал YouTube ({ch_id})"
        # twitch: https://www.theasmrindex.com/live/twitch/([a-zA-Z0-9_]+)
        m_tw = re.search(r'theasmrindex\.com/live/twitch/([a-zA-Z0-9_]+)', clean_url)
        if m_tw:
            tw_user = m_tw.group(1)
            return f"https://www.twitch.tv/{tw_user}", f"TheASMRIndex → Twitch ({tw_user})"

    return clean_url, ""


def _ssl_hint(error_msg: str) -> str:
    """Человекочитаемая подсказка к ошибкам сети/сертификатов/YouTube."""
    hints = []
    if 'CERTIFICATE_VERIFY_FAILED' in error_msg:
        hints.append(
            'Проверка сертификата видео-сервера не пройдена. '
            'Попробуйте: 1) запустить update.bat (обновит yt-dlp и certifi), '
            '2) установить обновления Windows, '
            '3) проверить, не подменяет ли сертификат антивирус или прокси.'
        )
    if any(k in error_msg for k in ('UNEXPECTED_EOF_WHILE_READING', '10054', 'Connection reset', 'timed out', 'EOF occurred', 'failed to receive handshake')):
        hints.append(
            'Сетевая ошибка соединения (сброс связи или таймаут). '
            'Для YouTube в РФ часто требуется включить VPN или указать прокси (socks5/http) в настройках.'
        )
    if any(k in error_msg for k in ('n challenge solving failed', 'Requested format is not available', 'Only images are available')):
        hints.append(
            'Не удалось расшифровать форматы YouTube (n challenge). '
            'Убедитесь, что установлен Node.js и запустите update.bat для обновления пакетов.'
        )
    if 'Sign in to confirm' in error_msg or 'bot' in error_msg.lower():
        hints.append(
            'Сервис запрашивает авторизацию или проверку бота. '
            'Выберите ваш браузер в поле "Cookies из браузера".'
        )
    return ('\n💡 ' + '\n💡 '.join(hints)) if hints else ''


class VideoDownloader:
    def __init__(self, progress_callback=None, log_callback=None, finish_callback=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.finish_callback = finish_callback
        self.is_downloading = False
        self.cancel_requested = False

    def cancel(self):
        """Запросить отмену текущей загрузки."""
        if self.is_downloading:
            self.cancel_requested = True
            if self.log_callback:
                self.log_callback("⚠️ Запрос на отмену загрузки...\n")

    def download(self, url, save_path, browser_for_cookies="", video_quality="best", proxy=""):
        if self.is_downloading:
            return
            
        self.is_downloading = True
        self.cancel_requested = False
        thread = threading.Thread(
            target=self._download_thread,
            args=(url, save_path, browser_for_cookies, video_quality, proxy)
        )
        thread.daemon = True
        thread.start()

    def get_formats(self, url, browser_for_cookies="", proxy=""):
        """Получить список доступных качеств для видео."""
        url, note = normalize_url(url)
        if note and self.log_callback:
            self.log_callback(f"ℹ️ {note}\n")

        # Специальная обработка QQASMR
        if "qqasmr.com" in url.lower():
            ok, data = extract_qqasmr_info(url, browser_for_cookies)
            if not ok:
                return False, data
            # Для QQASMR отдаем доступные варианты: 720p видео и аудио
            formats = [
                {'id': 'qq_video', 'label': '720p HD (MP4 Со звуком)', 'height': 720, 'tbr': 500, 'filesize': None}
            ]
            if data.get('audio_url'):
                formats.append(
                    {'id': 'qq_audio', 'label': 'Только аудио (M4A)', 'height': 0, 'tbr': 128, 'filesize': None}
                )
            return True, formats

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'remote_components': {'ejs:github'},
            'js_runtimes': _get_js_runtimes_config(),
            'logger': MyLogger(None)
        }
        if browser_for_cookies and browser_for_cookies != "Нет":
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies.lower(),)
            
        if proxy and proxy.strip():
            ydl_opts['proxy'] = proxy.strip()

        ffmpeg_exe = os.path.join(BASE_DIR, "ffmpeg.exe")
        if os.path.exists(ffmpeg_exe):
            ydl_opts['ffmpeg_location'] = BASE_DIR
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            formats = info.get('formats', [])
            results = {} 
            
            for f in formats:
                height = f.get('height')
                vcodec = f.get('vcodec')
                if height and vcodec and vcodec != 'none':
                    format_id = f.get('format_id')
                    fps = f.get('fps', '')
                    filesize = f.get('filesize') or f.get('filesize_approx')
                    tbr = f.get('tbr', 0)
                    
                    if filesize:
                        size_str = f"{filesize / (1024 * 1024):.1f} МБ"
                    else:
                        size_str = "Размер неизвестен"
                        
                    label = f"{height}p"
                    if fps and fps >= 50:
                        label += f" {fps}fps"
                    label += f" ({size_str})"

                    if height not in results:
                        results[height] = {'id': format_id, 'label': label, 'height': height, 'tbr': tbr, 'filesize': filesize}
                    else:
                        current = results[height]
                        if filesize and not current['filesize']:
                            results[height] = {'id': format_id, 'label': label, 'height': height, 'tbr': tbr, 'filesize': filesize}
                        elif tbr and current['tbr'] and tbr > current['tbr']:
                            results[height] = {'id': format_id, 'label': label, 'height': height, 'tbr': tbr, 'filesize': filesize}
                            
            sorted_formats = sorted(results.values(), key=lambda x: x['height'], reverse=True)
            return True, sorted_formats
        except Exception as e:
            error_msg = str(e)
            hint = _ssl_hint(error_msg)
            return False, error_msg + ('\n' + hint if hint else '')

    def _download_thread(self, url, save_path, browser_for_cookies, video_quality, proxy=""):
        url, note = normalize_url(url)
        if note and self.log_callback:
            self.log_callback(f"ℹ️ {note}\n")

        # 1. Если это QQASMR — получаем прямую подписанную ссылку
        custom_title = None
        if "qqasmr.com" in url.lower():
            if self.log_callback:
                self.log_callback("Авторизация и получение потока QQASMR...\n")
            ok, data = extract_qqasmr_info(url, browser_for_cookies)
            if not ok:
                if self.log_callback:
                    self.log_callback(f"Ошибка QQASMR: {data}\n")
                if self.finish_callback:
                    self.finish_callback(False, data, cancelled=False)
                self.is_downloading = False
                return
            
            custom_title = data['title']
            if video_quality == "qq_audio" and data.get('audio_url'):
                url = data['audio_url']
            else:
                url = data['video_url']

        # 2. Формируем формат скачивания
        format_string = 'bestvideo+bestaudio/best'
        if video_quality not in ("best", "qq_video", "qq_audio"):
            format_string = f"{video_quality}+bestaudio/{video_quality}/bestvideo+bestaudio/best"

        outtmpl_pattern = f'{save_path}/%(title)s.%(ext)s'
        if custom_title:
            outtmpl_pattern = f'{save_path}/{custom_title}.%(ext)s'

        ydl_opts = {
            'outtmpl': outtmpl_pattern,
            'progress_hooks': [self._hook],
            'logger': MyLogger(self.log_callback),
            'format': format_string,
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'remote_components': {'ejs:github'},
            'js_runtimes': _get_js_runtimes_config()
        }
        
        ffmpeg_exe = os.path.join(BASE_DIR, "ffmpeg.exe")
        if os.path.exists(ffmpeg_exe):
            ydl_opts['ffmpeg_location'] = BASE_DIR

        if browser_for_cookies and browser_for_cookies != "Нет" and "qqasmr.com" not in url:
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies.lower(),)
            
        if proxy and proxy.strip():
            ydl_opts['proxy'] = proxy.strip()

        cancelled = False
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if self.cancel_requested:
                cancelled = True
                if self.log_callback:
                    self.log_callback("🛑 Загрузка была отменена.\n")
                if self.finish_callback:
                    self.finish_callback(False, "Отменено пользователем", cancelled=True)
            else:
                if self.log_callback:
                    self.log_callback("✅ Скачивание завершено успешно!\n")
                if self.finish_callback:
                    self.finish_callback(True, "Успех", cancelled=False)

        except yt_dlp.utils.DownloadCancelled:
            cancelled = True
            if self.log_callback:
                self.log_callback("🛑 Загрузка успешно остановлена пользователем.\n")
            if self.finish_callback:
                self.finish_callback(False, "Отменено", cancelled=True)
        except Exception as e:
            if self.cancel_requested:
                cancelled = True
                if self.log_callback:
                    self.log_callback("🛑 Загрузка остановлена.\n")
                if self.finish_callback:
                    self.finish_callback(False, "Отменено", cancelled=True)
            else:
                error_msg = str(e)
                hint = _ssl_hint(error_msg)
                if hint:
                    error_msg = error_msg + '\n' + hint
                if self.log_callback:
                    self.log_callback(f"Ошибка: {error_msg}\n")
                if self.finish_callback:
                    self.finish_callback(False, error_msg, cancelled=False)
        finally:
            self.is_downloading = False
            self.cancel_requested = False

    def _hook(self, d):
        if self.cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("Загрузка отменена пользователем")

        status = d.get('status')
        if status == 'downloading':
            # Извлекаем процент скачивания
            percent_str = d.get('_percent_str', '0%').strip()
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            percent_str = ansi_escape.sub('', percent_str).replace('%', '')
            try:
                percent = float(percent_str) / 100.0
            except ValueError:
                percent = 0.0

            # Скорость
            speed = d.get('speed')
            if speed:
                if speed >= 1024 * 1024:
                    speed_str = f"{speed / (1024 * 1024):.2f} МБ/с"
                else:
                    speed_str = f"{speed / 1024:.1f} КБ/с"
            else:
                speed_str = d.get('_speed_str', '--').strip()
                speed_str = ansi_escape.sub('', speed_str)

            # ETA
            eta = d.get('eta')
            if eta is not None:
                mins, secs = divmod(int(eta), 60)
                hrs, mins = divmod(mins, 60)
                eta_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"
            else:
                eta_str = d.get('_eta_str', '--').strip()
                eta_str = ansi_escape.sub('', eta_str)

            # Размеры
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if total > 0:
                size_str = f"{downloaded / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} МБ"
            elif downloaded > 0:
                size_str = f"{downloaded / (1024 * 1024):.1f} МБ"
            else:
                size_str = "--"

            stats = {
                'percent': percent,
                'speed': speed_str,
                'eta': eta_str,
                'size': size_str,
                'status': 'Скачивание...'
            }

            if self.progress_callback:
                self.progress_callback(stats)

        elif status == 'finished':
            if self.progress_callback:
                self.progress_callback({
                    'percent': 1.0,
                    'speed': '--',
                    'eta': '00:00',
                    'size': 'Готово',
                    'status': 'Склейка / завершение...'
                })
            if self.log_callback:
                self.log_callback("Файл получен. Идет финализация/склейка потоков...\n")


class MyLogger:
    def __init__(self, log_callback):
        self.log_callback = log_callback

    def debug(self, msg):
        if not msg.startswith('[download]'):
            if self.log_callback:
                self.log_callback(msg + '\n')

    def info(self, msg):
        if self.log_callback:
            self.log_callback(msg + '\n')

    def warning(self, msg):
        if self.log_callback:
            self.log_callback(f"ПРЕДУПРЕЖДЕНИЕ: {msg}\n")

    def error(self, msg):
        if self.log_callback:
            self.log_callback(f"ОШИБКА: {msg}\n")


# Алиас для совместимости
VKDownloader = VideoDownloader
