import yt_dlp
import threading
import re
import os
import ssl
import sys
import base64
import contextlib


def _load_combined_certs(context, use_certifi=True):
    """Загрузить в SSL-контекст И certifi, И системные сертификаты.

    Почему это нужно: yt-dlp по умолчанию доверяет только своему бандлу
    certifi и игнорирует хранилище Windows. Поэтому видео, которое браузер
    открывает нормально (он смотрит в хранилище Windows), в приложении
    падало с CERTIFICATE_VERIFY_FAILED / unable to get local issuer
    certificate: корневого сертификата CDN VK просто не было в старом
    бандле certifi из venv. Проверка сертификатов при этом НЕ отключается:
    мы лишь расширяем список доверенных CA, а не принимаем любой сертификат.
    """
    # 1. certifi (Mozilla-корни, как раньше).
    with contextlib.suppress(Exception):
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    # 2. Системные пути по умолчанию (на Windows это в том числе
    # хранилище системы; учитывает и SSL_CERT_FILE из окружения).
    with contextlib.suppress(Exception):
        context.load_default_certs()
    # 3. Явно хранилище Windows: корневые и промежуточные CA, которых
    # может не быть в certifi (национальные CA, CA антивируса/прокси).
    # Браузеры Edge/Chrome доверяют именно им, поэтому видео у них работает.
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
    # 4. Явный бандл из окружения (корпоративный прокси и т.п.),
    # если он задан и не подхватился через load_default_certs().
    env_bundle = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
    if env_bundle and os.path.isfile(env_bundle):
        with contextlib.suppress(Exception):
            context.load_verify_locations(cafile=env_bundle)


def _install_combined_certs():
    """Подменить загрузку сертификатов yt-dlp на объединённую.

    Штатные urllib- и requests-хендлеры yt-dlp строят контекст через
    yt_dlp.networking._helper.make_ssl_context -> ssl_load_certs, поэтому
    подмены одной функции в этом модуле хватает и для метаданных, и для
    m3u8, и для фрагментов видео. Если внутренности yt-dlp изменятся,
    подмена молча не применится, а поведение останется прежним.
    """
    with contextlib.suppress(Exception):
        from yt_dlp.networking import _helper
        _helper.ssl_load_certs = _load_combined_certs


_install_combined_certs()


def _ssl_hint(error_msg):
    """Человекочитаемая подсказка к ошибке проверки сертификата."""
    if 'CERTIFICATE_VERIFY_FAILED' in error_msg:
        return (
            'Проверка сертификата видео-сервера не пройдена. '
            'Попробуйте: 1) запустить update.bat (обновит yt-dlp и certifi), '
            '2) установить обновления Windows, '
            '3) проверить, не подменяет ли сертификат антивирус или прокси. '
            'Проверка сертификатов намеренно не отключается.'
        )
    return ''


class VKDownloader:
    def __init__(self, progress_callback=None, log_callback=None, finish_callback=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.finish_callback = finish_callback
        self.is_downloading = False

    def download(self, url, save_path, browser_for_cookies="", video_quality="best"):
        if self.is_downloading:
            return
            
        self.is_downloading = True
        thread = threading.Thread(target=self._download_thread, args=(url, save_path, browser_for_cookies, video_quality))
        thread.daemon = True
        thread.start()

    def get_formats(self, url, browser_for_cookies=""):
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'logger': MyLogger(None) # Подавляем логи при поиске
        }
        if browser_for_cookies and browser_for_cookies != "Нет":
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies.lower(),)
            
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

    def _download_thread(self, url, save_path, browser_for_cookies, video_quality):
        format_string = 'bestvideo+bestaudio/best'
        if video_quality != "best":
            # Если конкретное качество не найдено (например, во втором видео в очереди), качаем лучшее
            format_string = f"{video_quality}+bestaudio/bestvideo+bestaudio/best"

        ydl_opts = {
            'outtmpl': f'{save_path}/%(title)s.%(ext)s',
            'progress_hooks': [self._hook],
            'logger': MyLogger(self.log_callback),
            'format': format_string,
            'merge_output_format': 'mp4'
        }
        
        # Если выбран браузер (а не "Нет"), передаем его в yt-dlp
        if browser_for_cookies and browser_for_cookies != "Нет":
            # yt-dlp ожидает tuple с именем браузера
            ydl_opts['cookiesfrombrowser'] = (browser_for_cookies.lower(),)
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if self.log_callback:
                self.log_callback("Скачивание завершено успешно!\n")
            if self.finish_callback:
                self.finish_callback(True, "Успех")
        except Exception as e:
            error_msg = str(e)
            hint = _ssl_hint(error_msg)
            if hint:
                error_msg = error_msg + '\n' + hint
            if self.log_callback:
                self.log_callback(f"Ошибка: {error_msg}\n")
            if self.finish_callback:
                self.finish_callback(False, error_msg)
        finally:
            self.is_downloading = False

    def _hook(self, d):
        if d['status'] == 'downloading':
            # Извлекаем процент скачивания
            percent_str = d.get('_percent_str', '0%').strip()
            # Убираем ANSI-коды (цвета в консоли), которые yt-dlp иногда добавляет
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            percent_str = ansi_escape.sub('', percent_str)
            percent_str = percent_str.replace('%', '')
            try:
                percent = float(percent_str) / 100.0
                if self.progress_callback:
                    self.progress_callback(percent)
            except ValueError:
                pass
            
            # Также можно выводить статус в лог, но чтобы не спамить, будем обновлять
            # только если это не засоряет текстовое поле. Мы ограничимся только процентами для UI.

        elif d['status'] == 'finished':
            if self.log_callback:
                self.log_callback("Файл скачан. Идет склейка видео и аудио (если требуется)...\n")

class MyLogger:
    def __init__(self, log_callback):
        self.log_callback = log_callback

    def debug(self, msg):
        # yt-dlp выводит обычные сообщения в debug. Игнорируем спам с [download]
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
