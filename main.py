import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import sys
import json
import subprocess
from downloader import VideoDownloader, VKDownloader, detect_platform

CONFIG_FILE = "config.json"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.load_config()

        # Настройка темы
        saved_mode = self.config.get("appearance_mode", "System")
        ctk.set_appearance_mode(saved_mode)
        ctk.set_default_color_theme("blue")

        # Настройки окна
        self.title("Media Downloader — VK, YouTube, ASMR")
        self.geometry("700x820")
        self.minsize(640, 750)

        # Ядро загрузчика
        self.downloader = VideoDownloader(
            progress_callback=self.update_progress,
            log_callback=self.update_log,
            finish_callback=self.download_finished
        )

        # Очередь скачивания
        self.download_queue = []
        self.total_files = 0
        self.current_file_index = 0
        self.is_running = False

        # Построение интерфейса
        self._build_ui()
        self.after(200, self._update_links_summary)

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
        if hasattr(self, "proxy_var"):
            self.config["proxy"] = self.proxy_var.get().strip()
        if hasattr(self, "browser_var"):
            self.config["browser"] = self.browser_var.get()
        if hasattr(self, "theme_var"):
            self.config["appearance_mode"] = self.theme_var.get()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def _build_ui(self):
        # Главный контейнер со скроллом на случай небольших экранов
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=15)

        # --- 1. ШАПКА ---
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="Media Downloader",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Загрузка видео и аудио с популярных сервисов",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        subtitle_lbl.pack(anchor="w")

        # Переключатель темы справа в шапке
        theme_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_box.pack(side="right", anchor="n")

        saved_theme = self.config.get("appearance_mode", "System")
        self.theme_var = ctk.StringVar(value=saved_theme)
        theme_menu = ctk.CTkOptionMenu(
            theme_box,
            values=["System", "Dark", "Light"],
            variable=self.theme_var,
            command=self._change_theme,
            width=100
        )
        theme_menu.pack(side="right")

        ctk.CTkLabel(theme_box, text="Тема:", font=ctk.CTkFont(size=12), text_color="gray").pack(side="right", padx=6)

        # Бейджи поддерживаемых сервисов
        badges_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        badges_frame.pack(fill="x", pady=(0, 10))

        badges = [
            ("VK Video", "#2787F5"),
            ("YouTube", "#FF0000"),
            ("TheASMRIndex", "#8A2BE2"),
            ("QQASMR", "#00B4D8")
        ]
        for name, col in badges:
            b = ctk.CTkLabel(
                badges_frame,
                text=f"  {name}  ",
                fg_color=col,
                text_color="white",
                corner_radius=6,
                font=ctk.CTkFont(size=11, weight="bold")
            )
            b.pack(side="left", padx=(0, 8))

        # --- 2. КАРТОЧКА ВВОДА ССЫЛОК ---
        input_card = ctk.CTkFrame(self.main_container, corner_radius=12)
        input_card.pack(fill="x", pady=6, padx=2)

        input_header = ctk.CTkFrame(input_card, fg_color="transparent")
        input_header.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            input_header,
            text="Ссылки на видео (каждая с новой строки):",
            font=ctk.CTkFont(size=13, weight="bold")
        )

        # Кнопки быстрых действий в шапке карточки
        actions_box = ctk.CTkFrame(input_header, fg_color="transparent")
        actions_box.pack(side="right")

        paste_btn = ctk.CTkButton(
            actions_box,
            text="📋 Вставить",
            width=85,
            height=26,
            command=self.paste_from_clipboard,
            font=ctk.CTkFont(size=12)
        )
        paste_btn.pack(side="left", padx=4)

        clear_btn = ctk.CTkButton(
            actions_box,
            text="🗑️ Очистить",
            width=85,
            height=26,
            fg_color="gray40",
            hover_color="gray30",
            command=self.clear_input,
            font=ctk.CTkFont(size=12)
        )
        clear_btn.pack(side="left", padx=4)

        self.url_textbox = ctk.CTkTextbox(input_card, height=85, font=ctk.CTkFont(size=12))
        self.url_textbox.pack(fill="x", padx=15, pady=(0, 6))
        self.url_textbox.bind("<KeyRelease>", lambda e: self._update_links_summary())

        # Динамический статус ссылок
        self.summary_label = ctk.CTkLabel(
            input_card,
            text="Ссылки не введены",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.summary_label.pack(anchor="w", padx=15, pady=(0, 10))

        # --- 3. КАРТОЧКА НАСТРОЕК ---
        settings_card = ctk.CTkFrame(self.main_container, corner_radius=12)
        settings_card.pack(fill="x", pady=6, padx=2)

        settings_title = ctk.CTkLabel(
            settings_card,
            text="Параметры загрузки",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        settings_title.pack(anchor="w", padx=15, pady=(12, 8))

        grid_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=15, pady=(0, 12))
        grid_frame.columnconfigure(1, weight=1)

        # 3.1 Браузер для Cookies
        ctk.CTkLabel(
            grid_frame,
            text="Cookies браузера:\n(нужно для приватных VK / QQASMR)",
            justify="left",
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))

        saved_browser = self.config.get("browser", "Нет")
        self.browser_var = ctk.StringVar(value=saved_browser)
        self.browser_combobox = ctk.CTkComboBox(
            grid_frame,
            values=["Нет", "Firefox", "Chrome", "Edge", "Opera", "Safari", "Vivaldi"],
            variable=self.browser_var,
            command=lambda v: self.save_config(),
            width=200
        )
        self.browser_combobox.grid(row=0, column=1, sticky="w", pady=6)

        # 3.2 Качество видео
        ctk.CTkLabel(
            grid_frame,
            text="Качество видео:",
            font=ctk.CTkFont(size=12)
        ).grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))

        quality_box = ctk.CTkFrame(grid_frame, fg_color="transparent")
        quality_box.grid(row=1, column=1, sticky="w", pady=6)

        self.quality_var = ctk.StringVar(value="Лучшее (Авто)")
        self.quality_combobox = ctk.CTkComboBox(
            quality_box,
            values=["Лучшее (Авто)"],
            variable=self.quality_var,
            width=200
        )
        self.quality_combobox.pack(side="left")

        self.fetch_quality_btn = ctk.CTkButton(
            quality_box,
            text="🔍 Получить качества",
            command=self.fetch_qualities,
            width=140
        )
        self.fetch_quality_btn.pack(side="left", padx=8)

        # 3.3 Прокси
        ctk.CTkLabel(
            grid_frame,
            text="Прокси (опционально):\n(socks5/http для YouTube/VPN)",
            justify="left",
            font=ctk.CTkFont(size=12)
        ).grid(row=2, column=0, sticky="w", pady=6, padx=(0, 10))

        saved_proxy = self.config.get("proxy", "")
        self.proxy_var = ctk.StringVar(value=saved_proxy)
        self.proxy_entry = ctk.CTkEntry(
            grid_frame,
            textvariable=self.proxy_var,
            placeholder_text="например: socks5://127.0.0.1:10808",
            width=350
        )
        self.proxy_entry.grid(row=2, column=1, sticky="ew", pady=6)

        # 3.4 Папка сохранения
        default_path = os.path.join(os.path.expanduser("~"), "Downloads")
        saved_path = self.config.get("save_path", default_path)
        if not os.path.exists(saved_path):
            saved_path = default_path
        self.save_path_var = ctk.StringVar(value=saved_path)

        ctk.CTkLabel(
            grid_frame,
            text="Папка сохранения:",
            font=ctk.CTkFont(size=12)
        ).grid(row=3, column=0, sticky="w", pady=6, padx=(0, 10))

        path_box = ctk.CTkFrame(grid_frame, fg_color="transparent")
        path_box.grid(row=3, column=1, sticky="ew", pady=6)

        choose_path_btn = ctk.CTkButton(
            path_box,
            text="Выбрать...",
            width=100,
            command=self.choose_directory
        )
        choose_path_btn.pack(side="left")

        open_folder_btn = ctk.CTkButton(
            path_box,
            text="📂 Открыть папку",
            width=120,
            fg_color="gray40",
            hover_color="gray30",
            command=self.open_save_folder
        )
        open_folder_btn.pack(side="left", padx=8)

        self.path_display = ctk.CTkLabel(
            grid_frame,
            textvariable=self.save_path_var,
            text_color="gray",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.path_display.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # --- 4. КАРТОЧКА ПРОГРЕССА И УПРАВЛЕНИЯ ---
        control_card = ctk.CTkFrame(self.main_container, corner_radius=12)
        control_card.pack(fill="x", pady=6, padx=2)

        # Кнопки "СКАЧАТЬ" и "ОТМЕНА"
        btn_box = ctk.CTkFrame(control_card, fg_color="transparent")
        btn_box.pack(fill="x", padx=15, pady=12)

        self.download_btn = ctk.CTkButton(
            btn_box,
            text="🚀 НАЧАТЬ СКАЧИВАНИЕ",
            command=self.start_download,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42
        )
        self.download_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.cancel_btn = ctk.CTkButton(
            btn_box,
            text="🛑 ОТМЕНА",
            command=self.cancel_download,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#D90429",
            hover_color="#EF233C",
            height=42,
            width=130,
            state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=(6, 0))

        # Статус очереди
        self.current_item_label = ctk.CTkLabel(
            control_card,
            text="Ожидание запуска...",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.current_item_label.pack(fill="x", padx=15, pady=(0, 4))

        # Прогресс-бар
        self.progress_bar = ctk.CTkProgressBar(control_card, height=14, corner_radius=7)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 6))

        # Подробная строка метрик (Скорость / Скачано / ETA)
        self.stats_label = ctk.CTkLabel(
            control_card,
            text="Скорость: --  |  Скачано: --  |  Осталось: --",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.stats_label.pack(fill="x", padx=15, pady=(0, 10))

        # --- 5. ЛОГ РАБОТЫ ---
        log_header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        log_header.pack(fill="x", pady=(4, 2))

        ctk.CTkLabel(
            log_header,
            text="Лог работы:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        clear_log_btn = ctk.CTkButton(
            log_header,
            text="Очистить лог",
            width=90,
            height=22,
            fg_color="transparent",
            text_color="gray",
            hover_color="gray25",
            font=ctk.CTkFont(size=11),
            command=self.clear_log
        )
        clear_log_btn.pack(side="right")

        self.log_box = ctk.CTkTextbox(self.main_container, height=120, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(fill="both", expand=True, pady=(0, 6))
        self.log_box.configure(state="disabled")

        self.format_map = {"Лучшее (Авто)": "best"}

    def _change_theme(self, mode):
        ctk.set_appearance_mode(mode)
        self.save_config()

    def paste_from_clipboard(self):
        try:
            text = self.clipboard_get()
            if text:
                current = self.url_textbox.get("1.0", "end").strip()
                if current:
                    self.url_textbox.insert("end", "\n" + text.strip())
                else:
                    self.url_textbox.delete("1.0", "end")
                    self.url_textbox.insert("1.0", text.strip())
                self._update_links_summary()
        except Exception:
            pass

    def clear_input(self):
        self.url_textbox.delete("1.0", "end")
        self._update_links_summary()

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def open_save_folder(self):
        path = self.save_path_var.get()
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        else:
            messagebox.showwarning("Внимание", f"Папка не существует:\n{path}")

    def _update_links_summary(self):
        urls_text = self.url_textbox.get("1.0", "end").strip()
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        if not urls:
            self.summary_label.configure(text="Ссылки не введены")
            return

        platforms = {}
        for u in urls:
            p = detect_platform(u)
            platforms[p] = platforms.get(p, 0) + 1

        details = ", ".join(f"{k}: {v}" for k, v in platforms.items())
        self.summary_label.configure(
            text=f"Всего ссылок: {len(urls)} ({details})",
            text_color="#2787F5"
        )

    def choose_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.save_path_var.set(folder_selected)
            self.save_config()

    def fetch_qualities(self):
        urls_text = self.url_textbox.get("1.0", "end").strip()
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        if not urls:
            messagebox.showwarning("Ошибка", "Пожалуйста, вставьте ссылку на видео!")
            return

        url = urls[0]
        self.save_config()

        self.fetch_quality_btn.configure(state="disabled", text="⏳ Проверка...")
        self.update_log(f"🔎 Запрос доступных качеств для первой ссылки: {url}\n")

        import threading
        thread = threading.Thread(
            target=self._fetch_qualities_thread,
            args=(url, self.browser_var.get(), self.proxy_var.get().strip())
        )
        thread.daemon = True
        thread.start()

    def _fetch_qualities_thread(self, url, browser, proxy):
        success, formats = self.downloader.get_formats(url, browser, proxy=proxy)

        def _update_ui():
            self.fetch_quality_btn.configure(state="normal", text="🔍 Получить качества")
            if success:
                self.format_map = {"Лучшее (Авто)": "best"}
                ui_values = ["Лучшее (Авто)"]
                for f in formats:
                    self.format_map[f['label']] = f['id']
                    ui_values.append(f['label'])

                self.quality_combobox.configure(values=ui_values)
                self.update_log(f"✅ Найдено доступных форматов: {len(formats)}\n")
                if len(ui_values) > 1:
                    self.quality_var.set(ui_values[1])
            else:
                self.update_log(f"❌ Ошибка получения качества:\n{formats}\n")
                messagebox.showerror("Ошибка", f"Не удалось получить список качеств:\n{formats}")

        self.after(0, _update_ui)

    def start_download(self):
        urls_text = self.url_textbox.get("1.0", "end").strip()
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]

        if not urls:
            messagebox.showwarning("Ошибка", "Пожалуйста, введите ссылки на видео!")
            return

        self.save_config()
        self.download_queue = urls
        self.total_files = len(urls)
        self.current_file_index = 0
        self.is_running = True

        self.download_btn.configure(state="disabled", text="⏳ СКАЧИВАНИЕ...")
        self.cancel_btn.configure(state="normal")

        self.download_next()

    def cancel_download(self):
        if self.is_running:
            self.cancel_btn.configure(state="disabled", text="⏳ Остановка...")
            self.update_log("\n⚠️ Остановка процесса и очистка очереди...\n")
            self.download_queue.clear()
            self.downloader.cancel()

    def download_next(self):
        if not self.download_queue or not self.is_running:
            self._finalize_all()
            return

        url = self.download_queue.pop(0)
        self.current_file_index += 1

        self.progress_bar.set(0)
        self.stats_label.configure(text="Скорость: --  |  Скачано: --  |  Осталось: --")
        platform = detect_platform(url)

        self.current_item_label.configure(
            text=f"[{self.current_file_index}/{self.total_files}] ({platform}) {url[:60]}..."
        )
        self.update_log(f"\n▶ [{self.current_file_index}/{self.total_files}] Начинаем загрузку ({platform}):\n{url}\n")

        format_id = self.format_map.get(self.quality_var.get(), "best")

        self.downloader.download(
            url=url,
            save_path=self.save_path_var.get(),
            browser_for_cookies=self.browser_var.get(),
            video_quality=format_id,
            proxy=self.proxy_var.get().strip()
        )

    def _finalize_all(self):
        self.is_running = False
        self.download_btn.configure(state="normal", text="🚀 НАЧАТЬ СКАЧИВАНИЕ")
        self.cancel_btn.configure(state="disabled", text="🛑 ОТМЕНА")
        self.current_item_label.configure(text="Все операции завершены.")
        self.progress_bar.set(1.0)
        self.update_log("\n🎉 Обработка всех элементов очереди завершена!\n")

    def update_progress(self, stats):
        def _apply():
            if isinstance(stats, dict):
                percent = stats.get('percent', 0.0)
                self.progress_bar.set(percent)
                speed = stats.get('speed', '--')
                size = stats.get('size', '--')
                eta = stats.get('eta', '--')
                status = stats.get('status', 'Скачивание...')
                self.stats_label.configure(
                    text=f"Скорость: {speed}  |  Скачано: {size}  |  Осталось: {eta}"
                )
            elif isinstance(stats, (int, float)):
                self.progress_bar.set(stats)
        self.after(0, _apply)

    def update_log(self, text):
        def _append_log():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _append_log)

    def download_finished(self, success, message, cancelled=False):
        def _handle_finish():
            if cancelled:
                self.update_log(f"🛑 Загрузка отменена: {message}\n")
                self._finalize_all()
                return

            if not success:
                self.update_log(f"❌ Ошибка при скачивании: {message}\n")

            # Переходим к следующему файлу в очереди
            self.download_next()

        self.after(0, _handle_finish)


if __name__ == "__main__":
    app = App()
    app.mainloop()
