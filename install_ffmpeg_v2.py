import urllib.request
import zipfile
import os
import shutil
import sys

url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
zip_path = "ffmpeg.zip"
extract_path = "ffmpeg_extracted"

def download_progress(count, block_size, total_size):
    global last_percent
    percent = int(count * block_size * 100 / total_size)
    if percent > last_percent:
        sys.stdout.write(f"\rСкачивание... {percent}%")
        sys.stdout.flush()
        last_percent = percent

last_percent = -1
print("Начинаю загрузку FFmpeg (около 130 МБ)...")
try:
    urllib.request.urlretrieve(url, zip_path, reporthook=download_progress)
    print("\nЗагрузка завершена! Распаковка...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)

    print("Копирование файлов...")
    shutil.move(os.path.join(extract_path, "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe"), "ffmpeg.exe")
    shutil.move(os.path.join(extract_path, "ffmpeg-master-latest-win64-gpl", "bin", "ffprobe.exe"), "ffprobe.exe")

    print("Очистка...")
    os.remove(zip_path)
    shutil.rmtree(extract_path)

    print("Успешно! Теперь можно скачивать видео со звуком.")
except Exception as e:
    print(f"\nОшибка при установке: {e}")
