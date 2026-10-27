import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import json
from downloader import VKDownloader

# Настройки внешнего вида (системная тема, синие акценты)
ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VK Video Downloader")
        self.geometry("600x650")
        self.resizable(False, False)

        self.load_config()

        # Инициализация нашего загрузчика
        self.downloader = VKDownloader(
            progress_callback=self.update_progress,
            log_callback=self.update_log,
            finish_callback=self.download_finished
        )

        # Очередь скачивания
        self.download_queue = []
        self.total_files = 0
        self.current_file_index = 0

        # Заголовок
        self.title_label = ctk.CTkLabel(self, text="Загрузчик видео из VK", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(15, 5))

        # Поле для ссылок (многострочное)
        self.url_label = ctk.CTkLabel(self, text="Вставьте ссылки на видео (каждая с новой строки):")
        self.url_label.pack(anchor="w", padx=50)
        
        self.url_textbox = ctk.CTkTextbox(self, width=500, height=80)
        self.url_textbox.pack(pady=(0, 10))

        # Блок настроек
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=5, padx=50, fill="x")

        # Выбор браузера для Cookies
        self.browser_label = ctk.CTkLabel(self.settings_frame, text="Cookies из браузера\n(нужно для приватных):")
        self.browser_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.browser_var = ctk.StringVar(value="Нет")
        self.browser_combobox = ctk.CTkComboBox(self.settings_frame, values=["Нет", "Chrome", "Edge", "Firefox", "Opera", "Safari", "Vivaldi"], variable=self.browser_var, width=150)
        self.browser_combobox.grid(row=0, column=1, padx=10, pady=10, sticky="e")

        # Выбор качества (Разрешение)
        self.format_label = ctk.CTkLabel(self.settings_frame, text="Качество видео:")
        self.format_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")

        self.quality_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.quality_frame.grid(row=1, column=1, padx=10, pady=10, sticky="e")

        self.quality_var = ctk.StringVar(value="Лучшее (Авто)")
        self.quality_combobox = ctk.CTkComboBox(self.quality_frame, values=["Лучшее (Авто)"], variable=self.quality_var, width=140)
        self.quality_combobox.pack(side="left")

        self.fetch_quality_btn = ctk.CTkButton(self.quality_frame, text="Получить", command=self.fetch_qualities, width=60)
        self.fetch_quality_btn.pack(side="left", padx=(5, 0))

        # Выбор папки для сохранения
        default_path = os.path.join(os.path.expanduser("~"), "Downloads")
        saved_path = self.config.get("save_path", default_path)
        if not os.path.exists(saved_path):
            saved_path = default_path
            
        self.save_path_var = ctk.StringVar(value=saved_path)
        
        self.path_label = ctk.CTkLabel(self.settings_frame, text="Папка сохранения:")
        self.path_label.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        
        self.path_button = ctk.CTkButton(self.settings_frame, text="Выбрать...", command=self.choose_directory, width=150)
        self.path_button.grid(row=2, column=1, padx=10, pady=10, sticky="e")
        
        self.path_display = ctk.CTkLabel(self.settings_frame, textvariable=self.save_path_var, text_color="gray", font=ctk.CTkFont(size=11))
        self.path_display.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        # Кнопка СКАЧАТЬ
        self.download_btn = ctk.CTkButton(self, text="СКАЧАТЬ", command=self.start_download, font=ctk.CTkFont(size=15, weight="bold"), height=40)
        self.download_btn.pack(pady=10)

        # Прогресс-бар
        self.progress_bar = ctk.CTkProgressBar(self, width=500)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0, 10))

        # Текстовое поле для логов (вывод статуса)
        self.log_box = ctk.CTkTextbox(self, width=500, height=100)
        self.log_box.pack(pady=5)
        self.log_box.configure(state="disabled")
        
        # Словарь для маппинга "Название в UI" -> "format_id"
        self.format_map = {"Лучшее (Авто)": "best"}

    def load_config(self):
        self.config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception:
                pass

    def save_config(self):
        self.config["save_path"] = self.save_path_var.get()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def fetch_qualities(self):
        urls_text = self.url_textbox.get("1.0", "end").strip()
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
        if not urls:
            messagebox.showwarning("Ошибка", "Пожалуйста, введите ссылку на видео перед получением качества!")
            return
            
        url = urls[0] # Берем первую ссылку для проверки доступных разрешений

        self.fetch_quality_btn.configure(state="disabled", text="...")
        self.update_log(f"Получение списка разрешений для первой ссылки...\n")
        
        import threading
        thread = threading.Thread(target=self._fetch_qualities_thread, args=(url, self.browser_var.get()))
        thread.daemon = True
        thread.start()

    def _fetch_qualities_thread(self, url, browser):
        success, formats = self.downloader.get_formats(url, browser)
        
        def _update_ui():
            self.fetch_quality_btn.configure(state="normal", text="Получить")
            if success:
                self.format_map = {"Лучшее (Авто)": "best"}
                ui_values = ["Лучшее (Авто)"]
                for f in formats:
                    self.format_map[f['label']] = f['id']
                    ui_values.append(f['label'])
                
                self.quality_combobox.configure(values=ui_values)
                self.update_log("Список разрешений успешно загружен!\n")
                if len(ui_values) > 1:
                    self.quality_var.set(ui_values[1])
            else:
                self.update_log(f"Ошибка получения качества: {formats}\n")
                messagebox.showerror("Ошибка", "Не удалось получить список разрешений.")
        
        self.after(0, _update_ui)

    def choose_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.save_path_var.set(folder_selected)
            self.save_config()

    def start_download(self):
        urls_text = self.url_textbox.get("1.0", "end").strip()
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
        
        if not urls:
            messagebox.showwarning("Ошибка", "Пожалуйста, введите ссылки на видео!")
            return

        self.download_queue = urls
        self.total_files = len(urls)
        self.current_file_index = 0

        self.download_btn.configure(state="disabled", text="СКАЧИВАНИЕ...")
        
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        
        self.download_next()

    def download_next(self):
        if not self.download_queue:
            self.download_btn.configure(state="normal", text="СКАЧАТЬ")
            self.progress_bar.set(1.0)
            self.update_log("\n🎉 Все загрузки завершены!\n")
            return

        url = self.download_queue.pop(0)
        self.current_file_index += 1
        
        self.progress_bar.set(0)
        self.update_log(f"\n[{self.current_file_index}/{self.total_files}] Запуск скачивания...\nURL: {url}\n")
        
        format_id = self.format_map.get(self.quality_var.get(), "best")
        
        self.downloader.download(
            url=url,
            save_path=self.save_path_var.get(),
            browser_for_cookies=self.browser_var.get(),
            video_quality=format_id
        )

    def update_progress(self, percent):
        self.after(0, lambda: self.progress_bar.set(percent))

    def update_log(self, text):
        def _append_log():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _append_log)

    def download_finished(self, success, message):
        def _handle_finish():
            if not success:
                self.update_log(f"Ошибка при скачивании: {message}\n")
            
            # Переходим к следующему файлу в очереди
            self.download_next()
            
        self.after(0, _handle_finish)

if __name__ == "__main__":
    app = App()
    app.mainloop()
