import yt_dlp
import threading
import re

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
            return False, str(e)

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
