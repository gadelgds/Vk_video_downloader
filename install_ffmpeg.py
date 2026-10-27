import urllib.request
import zipfile
import os
import shutil

url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
zip_path = "ffmpeg.zip"
extract_path = "ffmpeg_extracted"

print("Скачивание FFmpeg (это может занять пару минут)...")
urllib.request.urlretrieve(url, zip_path)

print("Распаковка...")
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

print("Установка файлов...")
shutil.move(os.path.join(extract_path, "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe"), "ffmpeg.exe")
shutil.move(os.path.join(extract_path, "ffmpeg-master-latest-win64-gpl", "bin", "ffprobe.exe"), "ffprobe.exe")

print("Очистка временных файлов...")
os.remove(zip_path)
shutil.rmtree(extract_path)

print("Готово! FFmpeg успешно установлен в папку проекта.")
