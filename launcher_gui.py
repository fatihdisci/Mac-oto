# launcher_gui.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Canvas, Listbox, Scrollbar, StringVar, messagebox
from typing import Callable

import requests

import customtkinter as ctk

from config import build_default_config
from models import MatchSelection, TeamRecord
from team_repository import TeamRepository
from tournament_manager import TournamentManager


# ============================================================
# GENEL SABITLER
# ============================================================

APP_WIDTH = 1280
APP_HEIGHT = 860

BASE_DIR = Path(__file__).resolve().parent
CFG = build_default_config()
REPOSITORY = TeamRepository(CFG.data_dir)
TOURNAMENT_MANAGER = TournamentManager(CFG.data_dir, REPOSITORY)

ENGINE_MODE_LABEL_TO_VALUE: dict[str, str] = {
    "1) Football SlowFast (1st/2nd Half HUD, Kirmizi-Yesil Civili)": "power_pegs",
    "2) Football Normal (1st/2nd Half HUD, Civisiz)": "normal",
    "3) Football VAR (Normal Pegs + VAR Review)": "football_var",
    "4) Football Result Guided Test (Normal Pegs, VAR Yok)": "football_result_guided_test",
    "5) Pop SlowFast (Progress Bar, Kirmizi-Yesil Civili)": "pop_power_pegs",
    "6) Pop Normal (Progress Bar, Civisiz)": "pop_normal",
    "7) Football Shifting (1st/2nd Half HUD, SlowFast Yok)": "football_shift",
    "8) Pop Shifting (Progress Bar, SlowFast Yok)": "pop_shift",
    "9) Football Blinking (Sadece Blinking Pegs)": "football_blink",
    "10) Pop Blinking (Sadece Blinking Pegs)": "pop_blink",
}
ENGINE_MODE_VALUE_TO_LABEL: dict[str, str] = {value: label for label, value in ENGINE_MODE_LABEL_TO_VALUE.items()}
ENGINE_MODE_VALUE_TO_LABEL.update(
    {
        "normal_shift": ENGINE_MODE_VALUE_TO_LABEL.get("football_shift", "Football Shifting"),
        "power_pegs_shift": ENGINE_MODE_VALUE_TO_LABEL.get("football_shift", "Football Shifting"),
        "pop_normal_shift": ENGINE_MODE_VALUE_TO_LABEL.get("pop_shift", "Pop Shifting"),
        "pop_power_pegs_shift": ENGINE_MODE_VALUE_TO_LABEL.get("pop_shift", "Pop Shifting"),
    }
)
DEFAULT_ENGINE_MODE_LABEL = next(iter(ENGINE_MODE_LABEL_TO_VALUE.keys()))
DEFAULT_ENGINE_MODE_VALUE = ENGINE_MODE_LABEL_TO_VALUE[DEFAULT_ENGINE_MODE_LABEL]

ENGINE_MODE_ALIASES_TO_CANONICAL: dict[str, str] = {
    "normal_shift": "football_shift",
    "power_pegs_shift": "football_shift",
    "pop_normal_shift": "pop_shift",
    "pop_power_pegs_shift": "pop_shift",
    "football_rail_test": "normal",
}
FOOTBALL_ENGINE_MODE_ITEMS: list[tuple[str, str]] = [
    (label, value)
    for label, value in ENGINE_MODE_LABEL_TO_VALUE.items()
    if not (value.startswith("pop_") or value == "pop_shift")
]
POP_ENGINE_MODE_ITEMS: list[tuple[str, str]] = [
    (label, value)
    for label, value in ENGINE_MODE_LABEL_TO_VALUE.items()
    if value.startswith("pop_") or value == "pop_shift"
]

TOURNAMENT_FORMAT_VALUES = ["4", "8", "16", "32", "48"]
TOURNAMENT_MODE_LABEL_TO_VALUE = {
    "Eleme Usulu": "elimination",
    "Playoff (Tek Ayak + ET/PEN)": "playoff",
}


# ============================================================
# YARDIMCI FONKSIYONLAR
# ============================================================

def open_folder_in_explorer(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ============================================================
# TAKIM SECIM PANELI (match_selector'dan gömülü)
# ============================================================

class TeamPickerPanel(ctk.CTkFrame):
    def __init__(self, master, title: str, repository: TeamRepository) -> None:
        super().__init__(master, corner_radius=16, fg_color="#0D1320")
        self.repository = repository
        self.selected_team: TeamRecord | None = None
        self.filtered_teams: list[TeamRecord] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#EEF2FA",
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self.league_var = StringVar(value="All Leagues")
        self.league_menu = ctk.CTkOptionMenu(
            self,
            values=["All Leagues"],
            variable=self.league_var,
            command=lambda _v: self.refresh_team_list(),
            height=32,
            fg_color="#1A2336",
            button_color="#2457F5",
        )
        self.league_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        self.search_entry = ctk.CTkEntry(
            self,
            placeholder_text="Takim ara...",
            height=32,
            fg_color="#0A111D",
            border_color="#243047",
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_team_list())

        list_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#0A111D")
        list_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 8))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.listbox = Listbox(
            list_frame,
            bg="#0A111D",
            fg="#F1F4FA",
            selectbackground="#2457F5",
            exportselection=False,
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 11),
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        self.listbox.bind("<<ListboxSelect>>", self._handle_listbox_select)

        scrollbar = Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.selection_label = ctk.CTkLabel(
            self,
            text="Secili takim: -",
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color="#AAB5CA",
        )
        self.selection_label.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

    def reload_leagues(self) -> None:
        try:
            leagues = self.repository.get_league_names()
        except Exception:
            leagues = ["All Leagues"]
        self.league_menu.configure(values=leagues)
        self.league_var.set("All Leagues")
        self.refresh_team_list()

    def refresh_team_list(self) -> None:
        query = self.search_entry.get()
        league_name = self.league_var.get()
        current_key = self.selected_team.team_key if self.selected_team else ""

        self.filtered_teams = self.repository.filter_teams(
            league_name=league_name,
            query=query,
        )

        self.listbox.delete(0, "end")
        for team in self.filtered_teams:
            self.listbox.insert("end", f"{team.name}  |  {team.league_name}")

        self.selected_team = next(
            (t for t in self.filtered_teams if t.team_key == current_key), None
        )
        self._sync_selection_ui()

    def _handle_listbox_select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            self.selected_team = None
            self._sync_selection_ui()
            return

        index = int(selection[0])
        if 0 <= index < len(self.filtered_teams):
            self.selected_team = self.filtered_teams[index]
        else:
            self.selected_team = None
        self._sync_selection_ui()

    def _sync_selection_ui(self) -> None:
        if not self.selected_team:
            self.selection_label.configure(text="Secili takim: -")
            return

        self.selection_label.configure(
            text=(
                f"Secili: {self.selected_team.name}\n"
                f"Lig: {self.selected_team.league_name}  |  Kisa: {self.selected_team.short_name}"
            )
        )

        try:
            index = next(
                idx
                for idx, team in enumerate(self.filtered_teams)
                if team.team_key == self.selected_team.team_key
            )
        except StopIteration:
            return

        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)


# ============================================================
# ANA LAUNCHER GUI — TEK PENCERE
# ============================================================

class MarbleRaceLauncherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Football Race Studio")
        self.minsize(1100, 750)
        self._set_startup_geometry()
        self.configure(fg_color="#0C111B")

        self.is_busy = False
        self.selected_engine_mode_value: str = DEFAULT_ENGINE_MODE_VALUE
        self._engine_mode_syncing = False
        self.current_tournament_state: dict | None = None
        self.tournament_selected_team_keys: list[str] = []
        self._tournament_available_keys: list[str] = []
        self._tournament_selected_keys_view: list[str] = []
        self._tournament_next_match_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabs()

        self.refresh_status()

    def _set_startup_geometry(self) -> None:
        screen_w = int(self.winfo_screenwidth())
        screen_h = int(self.winfo_screenheight())
        x = max(0, (screen_w - APP_WIDTH) // 2)
        y = max(0, ((screen_h - APP_HEIGHT) // 2) - 28)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}+{x}+{y}")

    # --------------------------------------------------------
    # UST BASLIK
    # --------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="#0E1525", height=70)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)

        title = ctk.CTkLabel(
            header,
            text="Football Race Studio",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="#F1F4FA",
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(14, 2))

        subtitle = ctk.CTkLabel(
            header,
            text="Takim havuzunu guncelle  >  Takimlari sec  >  Videoyu uret",
            font=ctk.CTkFont(size=13),
            text_color="#697A9B",
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 10))

    # --------------------------------------------------------
    # TAB SISTEMI
    # --------------------------------------------------------
    def _build_tabs(self) -> None:
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=14,
            fg_color="#111826",
            segmented_button_fg_color="#0D1320",
            segmented_button_selected_color="#2457F5",
            segmented_button_unselected_color="#1A2336",
        )
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))

        self.tab_main = self.tabview.add("Ana Panel")
        self.tab_teams = self.tabview.add("Takim Secimi")
        self.tab_tournament = self.tabview.add("Turnuva")
        self.tab_log = self.tabview.add("Islem Logu")

        self._build_main_tab()
        self._build_teams_tab()
        self._build_tournament_tab()
        self._build_log_tab()

    # --------------------------------------------------------
    # TAB 1: ANA PANEL
    # --------------------------------------------------------
    def _build_main_tab(self) -> None:
        tab = self.tab_main
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # --- Durum kartları ---
        cards_frame = ctk.CTkFrame(tab, fg_color="transparent")
        cards_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 12))
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.teams_card = self._create_status_card(
            cards_frame, "Takim Havuzu", "Kontrol ediliyor...", "JSON + logo verileri"
        )
        self.teams_card.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.match_card = self._create_status_card(
            cards_frame, "Secili Eslesme", "Kontrol ediliyor...", "Team A vs Team B"
        )
        self.match_card.grid(row=0, column=1, sticky="ew", padx=6)

        self.output_card = self._create_status_card(
            cards_frame, "Cikti Video", "Kontrol ediliyor...", "output_sim.mp4"
        )
        self.output_card.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # --- Aksiyon bloku ---
        action_frame = ctk.CTkFrame(tab, corner_radius=14, fg_color="#0D1320")
        action_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        action_frame.grid_columnconfigure((0, 1), weight=1)
        action_frame.grid_rowconfigure(0, weight=1)

        # Sol: Ana butonlar
        left = ctk.CTkFrame(action_frame, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)

        ctk.CTkLabel(
            left,
            text="Islem Adimlari",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F1F4FA",
        ).pack(anchor="w", pady=(0, 14))

        self.sync_button = ctk.CTkButton(
            left,
            text="1)  Takim Havuzunu Guncelle",
            height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2457F5",
            hover_color="#1B46C7",
            command=self.run_sync_teams,
        )
        self.sync_button.pack(fill="x", pady=(0, 10))

        self.selector_button = ctk.CTkButton(
            left,
            text="2)  Takim Sec  →",
            height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1D7A5A",
            hover_color="#165E45",
            command=self._go_to_team_tab,
        )
        self.selector_button.pack(fill="x", pady=(0, 10))

        self.render_button = ctk.CTkButton(
            left,
            text="3)  Videoyu Uret",
            height=52,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#B63D4B",
            hover_color="#932F3B",
            command=self.run_video_render,
        )
        self.render_button.pack(fill="x", pady=(8, 10))

        self.ai_text_button = ctk.CTkButton(
            left,
            text="4)  Aciklama ve Etiket Uret",
            height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#7A3B99",
            hover_color="#5D2A75",
            command=self.run_ai_text_generation,
        )
        self.ai_text_button.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            left,
            text=(
                "Onerilen sira:\n"
                "1. Takim havuzunu guncelle\n"
                "2. Takim Secimi sekmesine git\n"
                "3. Iki takimi sec ve kaydet\n"
                "4. Videoyu uret\n"
                "5. Aciklama ve etiket uret"
            ),
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#697A9B",
        ).pack(anchor="w", pady=(8, 0))

        # Sag: Yardimci islemler + secim bilgisi
        right = ctk.CTkFrame(action_frame, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)

        ctk.CTkLabel(
            right,
            text="Yardimci Islemler",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F1F4FA",
        ).pack(anchor="w", pady=(0, 14))

        btn_style = dict(height=40, fg_color="#1A2336", hover_color="#253352", font=ctk.CTkFont(size=13))

        self.refresh_button = ctk.CTkButton(
            right, text="Durumu Yenile", command=self.refresh_status, **btn_style
        )
        self.refresh_button.pack(fill="x", pady=(0, 8))

        self.restart_button = ctk.CTkButton(
            right,
            text="Uygulamayi Yeniden Baslat",
            command=self.restart_app,
            height=40,
            fg_color="#9B2D3A",
            hover_color="#7A2330",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.restart_button.pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            right, text="Data Klasorunu Ac",
            command=lambda: open_folder_in_explorer(CFG.data_dir), **btn_style
        ).pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            right, text="Output Dosyasini Ac",
            command=self.open_output_location, **btn_style
        ).pack(fill="x", pady=(0, 8))

        ctk.CTkButton(
            right, text="Logu Temizle",
            command=self.clear_log, **btn_style
        ).pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            right, text="Secili Eslesme Detayi",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#97A6C4",
        ).pack(anchor="w", pady=(4, 6))

        self.last_selection_box = ctk.CTkTextbox(
            right,
            height=100,
            corner_radius=10,
            fg_color="#0A0F18",
            border_width=1,
            border_color="#243047",
            font=ctk.CTkFont(size=12),
        )
        self.last_selection_box.pack(fill="both", expand=True, pady=(0, 0))
        self.last_selection_box.insert("1.0", "Secili eslesme bilgisi burada gorunecek.")
        self.last_selection_box.configure(state="disabled")

    # --------------------------------------------------------
    # TAB 2: TAKIM SECIMI (gömülü)
    # --------------------------------------------------------
    def _build_teams_tab(self) -> None:
        tab = self.tab_teams
        tab.grid_columnconfigure((0, 1), weight=1)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=0)

        self.team_a_panel = TeamPickerPanel(tab, "TEAM A", REPOSITORY)
        self.team_a_panel.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=(8, 8))

        self.team_b_panel = TeamPickerPanel(tab, "TEAM B", REPOSITORY)
        self.team_b_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=(8, 8))

        # Alt bilgi + kaydet
        footer = ctk.CTkFrame(tab, corner_radius=12, fg_color="#0D1320")
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        footer.grid_columnconfigure(0, weight=1)

        self.match_summary_label = ctk.CTkLabel(
            footer,
            text="Iki takimi sec ve kaydet.",
            justify="left",
            text_color="#D9E2F2",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.match_summary_label.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        self.real_fixture_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            footer,
            text="Bu eslesme gercek mac referansi",
            variable=self.real_fixture_var,
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        mode_row = ctk.CTkFrame(footer, fg_color="transparent")
        mode_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        mode_row.grid_columnconfigure((0, 1), weight=1)

        football_box = ctk.CTkFrame(mode_row, corner_radius=10, fg_color="#0A111D")
        football_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        football_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            football_box,
            text="Football Modlari",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#D9E2F2",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        self.football_mode_listbox = Listbox(
            football_box,
            height=6,
            bg="#0A111D",
            fg="#F1F4FA",
            selectbackground="#2457F5",
            selectforeground="#FFFFFF",
            exportselection=False,
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self.football_mode_listbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.football_mode_values: list[str] = []
        for label, value in FOOTBALL_ENGINE_MODE_ITEMS:
            self.football_mode_listbox.insert("end", label)
            self.football_mode_values.append(value)
        self.football_mode_listbox.bind("<<ListboxSelect>>", self._handle_football_mode_select)

        pop_box = ctk.CTkFrame(mode_row, corner_radius=10, fg_color="#0A111D")
        pop_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        pop_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pop_box,
            text="Pop Culture Modlari",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#D9E2F2",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        self.pop_mode_listbox = Listbox(
            pop_box,
            height=6,
            bg="#0A111D",
            fg="#F1F4FA",
            selectbackground="#2457F5",
            selectforeground="#FFFFFF",
            exportselection=False,
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self.pop_mode_listbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.pop_mode_values: list[str] = []
        for label, value in POP_ENGINE_MODE_ITEMS:
            self.pop_mode_listbox.insert("end", label)
            self.pop_mode_values.append(value)
        self.pop_mode_listbox.bind("<<ListboxSelect>>", self._handle_pop_mode_select)

        self.engine_mode_status_label = ctk.CTkLabel(
            footer,
            text="Aktif Motor: -",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#AFC1E8",
        )
        self.engine_mode_status_label.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 8))

        guided_row = ctk.CTkFrame(footer, fg_color="transparent")
        guided_row.grid(row=4, column=0, sticky="w", padx=16, pady=(0, 8))
        guided_row.grid_columnconfigure((0, 2), weight=0)

        self.guided_target_label = ctk.CTkLabel(
            guided_row,
            text="Guided Sonuc (A-B):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#D9E2F2",
        )
        self.guided_target_label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.guided_score_a_var = StringVar(value="2")
        self.guided_score_b_var = StringVar(value="1")
        self.guided_score_a_entry = ctk.CTkEntry(
            guided_row,
            width=54,
            height=30,
            textvariable=self.guided_score_a_var,
            justify="center",
            fg_color="#0A111D",
            border_color="#243047",
        )
        self.guided_score_a_entry.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            guided_row,
            text="-",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#AFC1E8",
        ).grid(row=0, column=2, sticky="w", padx=6)

        self.guided_score_b_entry = ctk.CTkEntry(
            guided_row,
            width=54,
            height=30,
            textvariable=self.guided_score_b_var,
            justify="center",
            fg_color="#0A111D",
            border_color="#243047",
        )
        self.guided_score_b_entry.grid(row=0, column=3, sticky="w")

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 12))
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            btn_row,
            text="Secimi Kaydet",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1C7B59",
            hover_color="#165E45",
            command=self._save_team_selection,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_row,
            text="Kaydet ve Videoyu Uret",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#B63D4B",
            hover_color="#932F3B",
            command=self._save_and_run_video_render,
        ).grid(row=0, column=1, sticky="ew", padx=6)

        ctk.CTkButton(
            btn_row,
            text="Ana Panele Don",
            height=42,
            font=ctk.CTkFont(size=14),
            fg_color="#3E4C66",
            hover_color="#2E3A51",
            command=lambda: self.tabview.set("Ana Panel"),
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # Periyodik ozet
        self._set_engine_mode_selection(DEFAULT_ENGINE_MODE_VALUE)
        self._update_guided_inputs_state()
        self._refresh_match_summary()
        self.after(800, self._periodic_match_summary)

    def _periodic_match_summary(self) -> None:
        self._refresh_match_summary()
        self.after(800, self._periodic_match_summary)

    def _refresh_match_summary(self) -> None:
        team_a = self.team_a_panel.selected_team
        team_b = self.team_b_panel.selected_team

        if not team_a or not team_b:
            self.match_summary_label.configure(
                text="Iki takimi de secmelisin.",
                text_color="#697A9B",
            )
            return

        title = f"{team_a.name} vs {team_b.name}"
        mode_label = ENGINE_MODE_VALUE_TO_LABEL.get(
            self.selected_engine_mode_value,
            self.selected_engine_mode_value,
        )
        guided_suffix = ""
        if self._is_guided_mode_selected():
            guided_suffix = f"  |  Guided: {self.guided_score_a_var.get().strip()}-{self.guided_score_b_var.get().strip()}"
        self.match_summary_label.configure(
            text=f"Video basligi:  {title}\nMotor: {mode_label}{guided_suffix}",
            text_color="#D9E2F2",
        )

    def _save_team_selection(self, show_success_popup: bool = True) -> bool:
        team_a = self.team_a_panel.selected_team
        team_b = self.team_b_panel.selected_team

        if not team_a or not team_b:
            messagebox.showerror("Eksik Secim", "Team A ve Team B secilmeden kayit yapilamaz.")
            return False

        if team_a.team_key == team_b.team_key:
            messagebox.showerror("Gecersiz Eslesme", "Ayni takim iki tarafa birden secilemez.")
            return False

        title = f"{team_a.name} vs {team_b.name}"
        engine_mode = self.selected_engine_mode_value
        guided_target_score_a: int | None = None
        guided_target_score_b: int | None = None
        if engine_mode == "football_result_guided_test":
            try:
                guided_target_score_a = int(self.guided_score_a_var.get().strip())
                guided_target_score_b = int(self.guided_score_b_var.get().strip())
            except ValueError:
                messagebox.showerror("Gecersiz Guided Sonuc", "Guided skor alanlari sayi olmali (ornek: 2-1).")
                return False
            if guided_target_score_a < 0 or guided_target_score_b < 0:
                messagebox.showerror("Gecersiz Guided Sonuc", "Guided skorlar negatif olamaz.")
                return False
            if guided_target_score_a > 20 or guided_target_score_b > 20:
                messagebox.showerror("Gecersiz Guided Sonuc", "Guided skorlar 0-20 araliginda olmali.")
                return False

        selection = MatchSelection(
            team_a=team_a,
            team_b=team_b,
            title=title,
            engine_mode=engine_mode,
            guided_target_score_a=guided_target_score_a,
            guided_target_score_b=guided_target_score_b,
            is_real_fixture_reference=self.real_fixture_var.get(),
        )

        output_path = REPOSITORY.save_selected_match(selection)
        self.refresh_status()
        if show_success_popup:
            messagebox.showinfo("Kaydedildi", f"Eslesme kaydedildi:\n{title}\n\n{output_path}")
        return True

    def _save_and_run_video_render(self) -> None:
        if not self._save_team_selection(show_success_popup=False):
            return
        self.log("Eslesme kaydedildi. Video uretim baslatiliyor...")
        self.run_video_render()

    # --------------------------------------------------------
    # TAB 3: TURNUVA
    # --------------------------------------------------------
    def _build_tournament_tab(self) -> None:
        tab = self.tab_tournament
        tab.grid_columnconfigure(0, weight=0)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, corner_radius=12, fg_color="#0D1320", width=370)
        left.grid(row=0, column=0, sticky="nsw", padx=(8, 6), pady=8)
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(
            left,
            text="Turnuva Kurulumu",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#F1F4FA",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        self.tournament_name_var = StringVar(value="Yeni Turnuva")
        ctk.CTkEntry(
            left,
            textvariable=self.tournament_name_var,
            height=32,
            fg_color="#0A111D",
            border_color="#243047",
            placeholder_text="Turnuva adi",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        format_row = ctk.CTkFrame(left, fg_color="transparent")
        format_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        format_row.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(format_row, text="Format:", text_color="#D9E2F2").grid(row=0, column=0, sticky="w")
        self.tournament_format_var = StringVar(value="16")
        ctk.CTkOptionMenu(
            format_row,
            values=TOURNAMENT_FORMAT_VALUES,
            variable=self.tournament_format_var,
            command=lambda _v: self._refresh_tournament_selected_list(),
            height=30,
            fg_color="#1A2336",
            button_color="#2457F5",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 10))

        ctk.CTkLabel(format_row, text="Mod:", text_color="#D9E2F2").grid(row=0, column=2, sticky="w")
        self.tournament_mode_label_var = StringVar(value="Eleme Usulu")
        ctk.CTkOptionMenu(
            format_row,
            values=list(TOURNAMENT_MODE_LABEL_TO_VALUE.keys()),
            variable=self.tournament_mode_label_var,
            height=30,
            fg_color="#1A2336",
            button_color="#2457F5",
        ).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        engine_row = ctk.CTkFrame(left, fg_color="transparent")
        engine_row.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        engine_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(engine_row, text="Motor:", text_color="#D9E2F2").grid(row=0, column=0, sticky="w")
        self.tournament_engine_label_var = StringVar(value=DEFAULT_ENGINE_MODE_LABEL)
        ctk.CTkOptionMenu(
            engine_row,
            values=list(ENGINE_MODE_LABEL_TO_VALUE.keys()),
            variable=self.tournament_engine_label_var,
            height=30,
            fg_color="#1A2336",
            button_color="#2457F5",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        team_filter_row = ctk.CTkFrame(left, fg_color="transparent")
        team_filter_row.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 6))
        team_filter_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(team_filter_row, text="Lig:", text_color="#D9E2F2").grid(row=0, column=0, sticky="w")
        self.tournament_league_var = StringVar(value="All Leagues")
        self.tournament_league_menu = ctk.CTkOptionMenu(
            team_filter_row,
            values=["All Leagues"],
            variable=self.tournament_league_var,
            command=lambda _v: self._refresh_tournament_available_list(),
            height=30,
            fg_color="#1A2336",
            button_color="#2457F5",
        )
        self.tournament_league_menu.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.tournament_search_entry = ctk.CTkEntry(
            left,
            placeholder_text="Takim ara...",
            height=30,
            fg_color="#0A111D",
            border_color="#243047",
        )
        self.tournament_search_entry.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.tournament_search_entry.bind("<KeyRelease>", lambda _e: self._refresh_tournament_available_list())

        list_row = ctk.CTkFrame(left, fg_color="transparent")
        list_row.grid(row=6, column=0, sticky="nsew", padx=12, pady=(0, 8))
        list_row.grid_columnconfigure((0, 2), weight=1)
        list_row.grid_rowconfigure(0, weight=1)

        self.tournament_available_listbox = Listbox(
            list_row,
            selectmode="extended",
            bg="#0A111D",
            fg="#F1F4FA",
            selectbackground="#2457F5",
            selectforeground="#FFFFFF",
            exportselection=False,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
            height=12,
        )
        self.tournament_available_listbox.grid(row=0, column=0, sticky="nsew")

        middle_btns = ctk.CTkFrame(list_row, fg_color="transparent", width=58)
        middle_btns.grid(row=0, column=1, sticky="ns", padx=8)
        ctk.CTkButton(
            middle_btns,
            text=">>",
            width=54,
            height=34,
            fg_color="#2457F5",
            hover_color="#1B46C7",
            command=self._add_tournament_selected_from_available,
        ).pack(pady=(8, 6))
        ctk.CTkButton(
            middle_btns,
            text="<<",
            width=54,
            height=34,
            fg_color="#3E4C66",
            hover_color="#2E3A51",
            command=self._remove_tournament_selected,
        ).pack(pady=6)

        self.tournament_selected_listbox = Listbox(
            list_row,
            selectmode="extended",
            bg="#0A111D",
            fg="#F1F4FA",
            selectbackground="#2457F5",
            selectforeground="#FFFFFF",
            exportselection=False,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
            height=12,
        )
        self.tournament_selected_listbox.grid(row=0, column=2, sticky="nsew")

        self.tournament_selected_count_label = ctk.CTkLabel(
            left,
            text="Secilen takim: 0 / 16",
            text_color="#AFC1E8",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.tournament_selected_count_label.grid(row=7, column=0, sticky="w", padx=12, pady=(0, 8))

        setup_btn_row = ctk.CTkFrame(left, fg_color="transparent")
        setup_btn_row.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 10))
        setup_btn_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            setup_btn_row,
            text="Rastgele Doldur",
            fg_color="#1D7A5A",
            hover_color="#165E45",
            command=self._autofill_tournament_selection,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            setup_btn_row,
            text="Secimi Temizle",
            fg_color="#3E4C66",
            hover_color="#2E3A51",
            command=self._clear_tournament_selection,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkButton(
            left,
            text="Turnuva Olustur",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#B63D4B",
            hover_color="#932F3B",
            command=self._create_tournament_from_ui,
        ).grid(row=9, column=0, sticky="ew", padx=12, pady=(0, 8))

        ctk.CTkButton(
            left,
            text="Son Turnuvayi Yukle",
            height=36,
            fg_color="#1A2336",
            hover_color="#253352",
            command=self._load_latest_tournament_into_ui,
        ).grid(row=10, column=0, sticky="ew", padx=12, pady=(0, 12))

        right = ctk.CTkFrame(tab, corner_radius=12, fg_color="#0D1320")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 8), pady=8)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        top_info = ctk.CTkFrame(right, fg_color="transparent")
        top_info.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
        top_info.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top_info,
            text="Turnuva Durumu",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F1F4FA",
        ).grid(row=0, column=0, sticky="w")

        action_row = ctk.CTkFrame(top_info, fg_color="transparent")
        action_row.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            action_row,
            text="Sıradaki Maci Takim Secimine Gonder",
            height=32,
            fg_color="#1A2336",
            hover_color="#253352",
            command=self._push_next_tournament_match_to_selection,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            action_row,
            text="Bracket Yenile",
            height=32,
            fg_color="#1A2336",
            hover_color="#253352",
            command=self._render_tournament_bracket,
        ).pack(side="left")
        ctk.CTkButton(
            action_row,
            text="Full Turnuva Run (Uzun)",
            height=32,
            fg_color="#1D7A5A",
            hover_color="#165E45",
            command=lambda: self._run_full_tournament_mode(layout="portrait_concat"),
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            action_row,
            text="Yatay Yayin Run",
            height=32,
            fg_color="#2457F5",
            hover_color="#1B46C7",
            command=lambda: self._run_full_tournament_mode(layout="landscape_broadcast"),
        ).pack(side="left", padx=(8, 0))

        self.tournament_status_box = ctk.CTkTextbox(
            top_info,
            height=78,
            fg_color="#0A0F18",
            border_width=1,
            border_color="#243047",
            font=ctk.CTkFont(size=12),
        )
        self.tournament_status_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.tournament_status_box.insert("1.0", "Turnuva henuz olusturulmadi.")
        self.tournament_status_box.configure(state="disabled")

        canvas_container = ctk.CTkFrame(right, fg_color="#0A111D")
        canvas_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        canvas_container.grid_columnconfigure(0, weight=1)
        canvas_container.grid_rowconfigure(0, weight=1)

        self.tournament_bracket_canvas = Canvas(
            canvas_container,
            bg="#0A111D",
            highlightthickness=0,
            bd=0,
        )
        self.tournament_bracket_canvas.grid(row=0, column=0, sticky="nsew")
        self.tournament_bracket_canvas.bind("<Configure>", lambda _e: self._render_tournament_bracket())

        next_row = ctk.CTkFrame(right, fg_color="transparent")
        next_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        next_row.grid_columnconfigure(0, weight=1)

        self.tournament_next_match_label = ctk.CTkLabel(
            next_row,
            text="Sıradaki maç: -",
            text_color="#D9E2F2",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.tournament_next_match_label.grid(row=0, column=0, sticky="w")

        score_row = ctk.CTkFrame(next_row, fg_color="transparent")
        score_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.tournament_score_a_var = StringVar(value="1")
        self.tournament_score_b_var = StringVar(value="0")
        ctk.CTkEntry(
            score_row,
            width=64,
            height=30,
            textvariable=self.tournament_score_a_var,
            justify="center",
            fg_color="#0A111D",
            border_color="#243047",
        ).pack(side="left")
        ctk.CTkLabel(score_row, text="-", text_color="#D9E2F2").pack(side="left", padx=8)
        ctk.CTkEntry(
            score_row,
            width=64,
            height=30,
            textvariable=self.tournament_score_b_var,
            justify="center",
            fg_color="#0A111D",
            border_color="#243047",
        ).pack(side="left")
        ctk.CTkButton(
            score_row,
            text="Sonucu Isle",
            height=30,
            fg_color="#2457F5",
            hover_color="#1B46C7",
            command=self._record_tournament_match_result,
        ).pack(side="left", padx=(10, 0))

        self._refresh_tournament_team_filters()
        self._refresh_tournament_available_list()
        self._refresh_tournament_selected_list()
        self._update_tournament_status_box()
        self._update_tournament_next_match_panel()

    def _required_tournament_team_count(self) -> int:
        try:
            return int(self.tournament_format_var.get())
        except Exception:
            return 16

    def _refresh_tournament_team_filters(self) -> None:
        try:
            leagues = REPOSITORY.get_league_names()
        except Exception:
            leagues = ["All Leagues"]
        self.tournament_league_menu.configure(values=leagues)
        if self.tournament_league_var.get() not in leagues:
            self.tournament_league_var.set("All Leagues")

    def _refresh_tournament_available_list(self) -> None:
        league = self.tournament_league_var.get()
        query = self.tournament_search_entry.get().strip()
        try:
            teams = REPOSITORY.filter_teams(league_name=league, query=query)
        except Exception:
            teams = []

        self._tournament_available_keys = [team.team_key for team in teams if team.team_key not in set(self.tournament_selected_team_keys)]
        self.tournament_available_listbox.delete(0, "end")
        for team in teams:
            if team.team_key in set(self.tournament_selected_team_keys):
                continue
            self.tournament_available_listbox.insert("end", f"{team.name}  |  {team.league_name}")

    def _refresh_tournament_selected_list(self) -> None:
        required = self._required_tournament_team_count()
        self._tournament_selected_keys_view = list(self.tournament_selected_team_keys)
        self.tournament_selected_listbox.delete(0, "end")
        for key in self._tournament_selected_keys_view:
            team = REPOSITORY.get_team_by_key(key)
            if team is None:
                continue
            self.tournament_selected_listbox.insert("end", f"{team.name}  |  {team.league_name}")

        self.tournament_selected_count_label.configure(
            text=f"Secilen takim: {len(self.tournament_selected_team_keys)} / {required}"
        )
        self._refresh_tournament_available_list()

    def _add_tournament_selected_from_available(self) -> None:
        required = self._required_tournament_team_count()
        indices = self.tournament_available_listbox.curselection()
        if not indices:
            return
        for idx in indices:
            if len(self.tournament_selected_team_keys) >= required:
                break
            i = int(idx)
            if 0 <= i < len(self._tournament_available_keys):
                key = self._tournament_available_keys[i]
                if key not in self.tournament_selected_team_keys:
                    self.tournament_selected_team_keys.append(key)
        self._refresh_tournament_selected_list()

    def _remove_tournament_selected(self) -> None:
        indices = sorted((int(i) for i in self.tournament_selected_listbox.curselection()), reverse=True)
        if not indices:
            return
        for idx in indices:
            if 0 <= idx < len(self._tournament_selected_keys_view):
                key = self._tournament_selected_keys_view[idx]
                self.tournament_selected_team_keys = [k for k in self.tournament_selected_team_keys if k != key]
        self._refresh_tournament_selected_list()

    def _autofill_tournament_selection(self) -> None:
        required = self._required_tournament_team_count()
        query = self.tournament_search_entry.get().strip()
        league = self.tournament_league_var.get()
        pool = REPOSITORY.filter_teams(league_name=league, query=query)
        keys = [team.team_key for team in pool if team.team_key]
        if len(keys) < required:
            keys = [team.team_key for team in REPOSITORY.load_teams() if team.team_key]
        self.tournament_selected_team_keys = keys[:required]
        self._refresh_tournament_selected_list()

    def _clear_tournament_selection(self) -> None:
        self.tournament_selected_team_keys = []
        self._refresh_tournament_selected_list()

    def _create_tournament_from_ui(self) -> None:
        if not REPOSITORY.exists():
            messagebox.showerror("Takim Havuzu Gerekli", "Once takim havuzunu guncellemelisin.")
            return

        required = self._required_tournament_team_count()
        if len(self.tournament_selected_team_keys) != required:
            messagebox.showerror(
                "Eksik Takim",
                f"Turnuva olusturmak icin tam {required} takim secmelisin.",
            )
            return

        mode_label = self.tournament_mode_label_var.get()
        tournament_mode = TOURNAMENT_MODE_LABEL_TO_VALUE.get(mode_label, "elimination")
        engine_label = self.tournament_engine_label_var.get()
        engine_mode = ENGINE_MODE_LABEL_TO_VALUE.get(engine_label, DEFAULT_ENGINE_MODE_VALUE)

        try:
            state = TOURNAMENT_MANAGER.create_tournament(
                name=self.tournament_name_var.get().strip(),
                format_size=required,
                tournament_mode=tournament_mode,
                team_keys=list(self.tournament_selected_team_keys),
                engine_mode=engine_mode,
                is_real_fixture_reference=False,
            )
        except Exception as exc:
            messagebox.showerror("Turnuva Olusturma Hatasi", str(exc))
            return

        self.current_tournament_state = state
        self._update_tournament_status_box()
        self._update_tournament_next_match_panel()
        self._render_tournament_bracket()
        match_row = next((m for m in state.get("matches", []) if str(m.get("id")) == str(match_id)), None)
        decided_by = str((match_row or {}).get("decided_by") or "normal_time")
        final_a = int((match_row or {}).get("score_a") or score_a)
        final_b = int((match_row or {}).get("score_b") or score_b)
        self.log(
            f"Turnuva sonucu islendi: {score_a}-{score_b} -> {final_a}-{final_b} "
            f"({decided_by}, mac: {match_id})"
        )
        self.log(f"Turnuva olusturuldu: {state.get('name')} ({required} takim)")

    def _load_latest_tournament_into_ui(self) -> None:
        state = TOURNAMENT_MANAGER.load_latest_tournament()
        if state is None:
            messagebox.showinfo("Turnuva", "Kayitli turnuva bulunamadi.")
            return

        self.current_tournament_state = state
        self.tournament_name_var.set(str(state.get("name", "Turnuva")))
        self.tournament_format_var.set(str(state.get("format_size", "16")))
        mode_val = str(state.get("tournament_mode", "elimination"))
        mode_label = next((k for k, v in TOURNAMENT_MODE_LABEL_TO_VALUE.items() if v == mode_val), "Eleme Usulu")
        self.tournament_mode_label_var.set(mode_label)
        self.tournament_selected_team_keys = list(state.get("team_keys", []))

        engine_mode = str(state.get("engine_mode", DEFAULT_ENGINE_MODE_VALUE))
        self.tournament_engine_label_var.set(ENGINE_MODE_VALUE_TO_LABEL.get(engine_mode, DEFAULT_ENGINE_MODE_LABEL))

        self._refresh_tournament_selected_list()
        self._update_tournament_status_box()
        self._update_tournament_next_match_panel()
        self._render_tournament_bracket()
        self.log(f"Turnuva yuklendi: {state.get('name')}")

    def _update_tournament_status_box(self) -> None:
        if not self.current_tournament_state:
            text = "Turnuva henuz olusturulmadi."
        else:
            state = self.current_tournament_state
            champion_key = TOURNAMENT_MANAGER.get_champion_key(state)
            champion_name = TOURNAMENT_MANAGER.get_team_name(champion_key) if champion_key else "-"
            mode_val = str(state.get("tournament_mode", "elimination"))
            mode_label = next((k for k, v in TOURNAMENT_MODE_LABEL_TO_VALUE.items() if v == mode_val), mode_val)
            text = (
                f"Turnuva: {state.get('name', '-')}\n"
                f"Format: {state.get('format_size', '-')}  |  Mod: {mode_label}\n"
                f"Durum: {state.get('status', '-')}\n"
                f"Sampiyon: {champion_name}"
            )
        self.tournament_status_box.configure(state="normal")
        self.tournament_status_box.delete("1.0", "end")
        self.tournament_status_box.insert("1.0", text)
        self.tournament_status_box.configure(state="disabled")

    def _update_tournament_next_match_panel(self) -> None:
        if not self.current_tournament_state:
            self.tournament_next_match_label.configure(text="Sıradaki maç: -")
            self._tournament_next_match_id = None
            return

        nxt = TOURNAMENT_MANAGER.get_next_match(self.current_tournament_state)
        if nxt is None:
            champion = TOURNAMENT_MANAGER.get_team_name(
                TOURNAMENT_MANAGER.get_champion_key(self.current_tournament_state)
            )
            self.tournament_next_match_label.configure(text=f"Turnuva tamamlandi. Sampiyon: {champion}")
            self._tournament_next_match_id = None
            return

        team_a_name = TOURNAMENT_MANAGER.get_team_name(nxt.get("team_a_key"))
        team_b_name = TOURNAMENT_MANAGER.get_team_name(nxt.get("team_b_key"))
        round_name = str(nxt.get("round_name", "Round"))
        series_suffix = ""
        wins_needed = int(nxt.get("wins_needed", 1))
        if wins_needed > 1:
            series_suffix = f"  |  Seri: {int(nxt.get('wins_a', 0))}-{int(nxt.get('wins_b', 0))} (BO{wins_needed * 2 - 1})"
        self.tournament_next_match_label.configure(
            text=f"Sıradaki maç: {round_name} | {team_a_name} vs {team_b_name}{series_suffix}"
        )
        self._tournament_next_match_id = str(nxt.get("id"))

    def _record_tournament_match_result(self) -> None:
        if not self.current_tournament_state:
            messagebox.showerror("Turnuva Yok", "Once turnuva olustur veya yukle.")
            return
        match_id = getattr(self, "_tournament_next_match_id", None)
        if not match_id:
            messagebox.showinfo("Turnuva", "Islenecek siradaki mac bulunamadi.")
            return
        try:
            score_a = int(self.tournament_score_a_var.get().strip())
            score_b = int(self.tournament_score_b_var.get().strip())
        except ValueError:
            messagebox.showerror("Skor Hatasi", "Skorlar sayi olmali.")
            return

        try:
            state = TOURNAMENT_MANAGER.record_match_result_with_knockout_rules(
                state=self.current_tournament_state,
                match_id=match_id,
                score_a=score_a,
                score_b=score_b,
            )
        except Exception as exc:
            messagebox.showerror("Sonuc Isleme Hatasi", str(exc))
            return

        self.current_tournament_state = state
        self._update_tournament_status_box()
        self._update_tournament_next_match_panel()
        self._render_tournament_bracket()

    def _push_next_tournament_match_to_selection(self) -> None:
        if not self.current_tournament_state:
            messagebox.showerror("Turnuva Yok", "Once turnuva olustur veya yukle.")
            return
        nxt = TOURNAMENT_MANAGER.get_next_match(self.current_tournament_state)
        if nxt is None:
            messagebox.showinfo("Turnuva", "Siradaki mac bulunamadi.")
            return
        try:
            selection = TOURNAMENT_MANAGER.build_match_selection(self.current_tournament_state, nxt)
        except Exception as exc:
            messagebox.showerror("Match Aktarim Hatasi", str(exc))
            return

        REPOSITORY.save_selected_match(selection)
        self.refresh_status()
        self.team_a_panel.selected_team = selection.team_a
        self.team_b_panel.selected_team = selection.team_b
        self.real_fixture_var.set(selection.is_real_fixture_reference)
        self._set_engine_mode_selection(selection.engine_mode)
        self.team_a_panel._sync_selection_ui()
        self.team_b_panel._sync_selection_ui()
        self._refresh_match_summary()
        self.tabview.set("Takim Secimi")
        self.log(f"Turnuva maci secime aktarildi: {selection.title}")

    def _render_tournament_bracket(self) -> None:
        if not hasattr(self, "tournament_bracket_canvas"):
            return

        canvas = self.tournament_bracket_canvas
        canvas.delete("all")

        state = self.current_tournament_state
        if not state:
            canvas.create_text(20, 20, text="Turnuva henuz olusturulmadi.", anchor="nw", fill="#7D8EAF", font=("Segoe UI", 12, "bold"))
            return

        rounds = TOURNAMENT_MANAGER.get_round_matches(state)
        if not rounds:
            canvas.create_text(20, 20, text="Bracket verisi bulunamadi.", anchor="nw", fill="#7D8EAF", font=("Segoe UI", 12, "bold"))
            return

        width = max(760, int(canvas.winfo_width() or 760))
        height = max(500, int(canvas.winfo_height() or 500))
        margin_x = 18
        margin_y = 42
        col_count = max(1, len(rounds))
        col_w = max(140, int((width - margin_x * 2) / col_count))

        # --- 1. Geçiş: Pozisyon hesapla ---
        # Önce parent→children haritasını oluştur
        all_matches_by_id: dict[str, dict] = {str(m.get("id")): m for m in state.get("matches", [])}
        parent_to_child_ids: dict[str, list[str]] = {}
        for m in state.get("matches", []):
            pid = str(m.get("winner_to_match_id") or "")
            cid = str(m.get("id"))
            if pid:
                parent_to_child_ids.setdefault(pid, []).append(cid)

        pos: dict[str, tuple[float, float, float, float]] = {}

        # Round 0: eşit spacing
        first_col_idx, (_first_ridx, first_matches) = next(
            ((ci, rv) for ci, rv in enumerate(rounds)), (0, (0, []))
        )
        if first_matches:
            spacing0 = (height - margin_y * 2) / (len(first_matches) + 1)
            for midx, match in enumerate(first_matches):
                col_idx = first_col_idx
                x1 = margin_x + col_idx * col_w + 6
                x2 = x1 + col_w - 18
                cy = margin_y + (midx + 1) * spacing0
                pos[str(match.get("id"))] = (x1, x2, cy, cy)

        # Sonraki turlar: child'ların ortası
        for col_idx, (_round_idx, matches) in enumerate(rounds[1:], start=1):
            for match in matches:
                mid = str(match.get("id"))
                x1 = margin_x + col_idx * col_w + 6
                x2 = x1 + col_w - 18
                children = parent_to_child_ids.get(mid, [])
                child_cys = [pos[cid][2] for cid in children if cid in pos]
                if child_cys:
                    cy = sum(child_cys) / len(child_cys)
                else:
                    # Fallback: eşit spacing
                    spacing_fb = (height - margin_y * 2) / (len(matches) + 1)
                    order = int(match.get("order", 0))
                    cy = margin_y + (order + 1) * spacing_fb
                pos[mid] = (x1, x2, cy, cy)

        # --- 2. Geçiş: Maç kutularını çiz ---
        for col_idx, (_round_idx, matches) in enumerate(rounds):
            if not matches:
                continue
            title = str(matches[0].get("round_name") or f"Round {col_idx + 1}")
            tx = margin_x + col_idx * col_w + col_w / 2
            canvas.create_text(tx, 18, text=title, fill="#AFC1E8", font=("Segoe UI", 10, "bold"))

            for match in matches:
                mid = str(match.get("id"))
                if mid not in pos:
                    continue
                x1, x2, cy, _ = pos[mid]
                y1 = cy - 24
                y2 = cy + 24

                status = str(match.get("status", "pending"))
                fill = "#13233A"
                border = "#2D4368"
                if status == "completed":
                    fill = "#163323"
                    border = "#2F7A51"
                elif status == "active_series":
                    fill = "#2E2A16"
                    border = "#8E7A3C"

                canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=border, width=2)

                team_a = TOURNAMENT_MANAGER.get_team_name(match.get("team_a_key"))
                team_b = TOURNAMENT_MANAGER.get_team_name(match.get("team_b_key"))
                if match.get("score_a") is not None and match.get("score_b") is not None:
                    decided_by = str(match.get("decided_by") or "normal_time")
                    if decided_by == "penalties":
                        reg_a = int(match.get("regular_time_score_a", match.get("score_a", 0)))
                        reg_b = int(match.get("regular_time_score_b", match.get("score_b", 0)))
                        pen_a = int(match.get("penalty_score_a", 0))
                        pen_b = int(match.get("penalty_score_b", 0))
                        score_text = f"{reg_a}-{reg_b} P{pen_a}-{pen_b}"
                    elif decided_by == "extra_time":
                        reg_a = int(match.get("regular_time_score_a", 0))
                        reg_b = int(match.get("regular_time_score_b", 0))
                        et_a = int(match.get("extra_time_score_a", 0))
                        et_b = int(match.get("extra_time_score_b", 0))
                        score_text = f"{reg_a}-{reg_b} ET{et_a}-{et_b}"
                    else:
                        score_text = f"{int(match.get('score_a', 0))}-{int(match.get('score_b', 0))}"
                else:
                    score_text = "-:-"

                canvas.create_text(x1 + 8, y1 + 13, text=self._clip_text(team_a, 18), anchor="w", fill="#EEF2FA", font=("Segoe UI", 9, "bold"))
                canvas.create_text(x1 + 8, y2 - 13, text=self._clip_text(team_b, 18), anchor="w", fill="#D9E2F2", font=("Segoe UI", 9))
                canvas.create_text(x2 - 8, cy, text=score_text, anchor="e", fill="#BFD2F6", font=("Consolas", 10, "bold"))

        # --- 3. Geçiş: Bağlantı çizgileri (staple şekli) ---
        for parent_id, children in parent_to_child_ids.items():
            if parent_id not in pos:
                continue
            px1, _px2, py, _ = pos[parent_id]
            child_cys = [pos[cid][2] for cid in children if cid in pos]
            if not child_cys:
                continue
            cx2 = pos[children[0]][1]
            midx = (cx2 + px1) / 2.0
            for cy in child_cys:
                canvas.create_line(cx2, cy, midx, cy, fill="#4F6EA0", width=2)
            canvas.create_line(midx, min(child_cys), midx, max(child_cys), fill="#4F6EA0", width=2)
            canvas.create_line(midx, py, px1, py, fill="#4F6EA0", width=2)

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        clean = (text or "").strip()
        if len(clean) <= limit:
            return clean
        return clean[: max(1, limit - 1)] + "…"

    # --------------------------------------------------------
    # TAB 4: ISLEM LOGU
    # --------------------------------------------------------
    def _build_log_tab(self) -> None:
        tab = self.tab_log
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(
            tab,
            corner_radius=10,
            fg_color="#0A0F18",
            border_width=1,
            border_color="#243047",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 8))
        self.log_box.insert("1.0", "Launcher hazir.\n")
        self.log_box.configure(state="disabled")

    # --------------------------------------------------------
    # LOG YARDIMCILARI
    # --------------------------------------------------------
    def log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text.rstrip() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", "Log temizlendi.\n")
        self.log_box.configure(state="disabled")

    # --------------------------------------------------------
    # DURUM YENILEME
    # --------------------------------------------------------
    def refresh_status(self) -> None:
        self._refresh_team_pool_status()
        self._refresh_selected_match_status()
        self._refresh_output_status()

    def _refresh_team_pool_status(self) -> None:
        if not REPOSITORY.exists():
            self._set_card_text(
                self.teams_card,
                value_text="Takim havuzu yok",
                subtitle="Once takim havuzunu guncellemelisin",
            )
            return

        try:
            teams = REPOSITORY.load_teams(force_reload=True)
            leagues = REPOSITORY.get_league_names()
            league_count = max(0, len(leagues) - 1)

            self._set_card_text(
                self.teams_card,
                value_text=f"{len(teams)} takim",
                subtitle=f"{league_count} lig hazir",
            )
        except Exception as exc:
            self._set_card_text(
                self.teams_card,
                value_text="Hata",
                subtitle=str(exc),
            )

    def _refresh_selected_match_status(self) -> None:
        match = REPOSITORY.load_selected_match()

        if match is None:
            self._set_card_text(
                self.match_card,
                value_text="Secim yok",
                subtitle="Henuz eslesme kaydedilmedi",
            )
            self._set_selection_text("Henuz kayitli eslesme yok.")
            return

        self._set_card_text(
            self.match_card,
            value_text=f"{match.team_a.name} vs {match.team_b.name}",
            subtitle="Secim dosyasi hazir",
        )

        info_lines = [
            f"Team A: {match.team_a.name} ({match.team_a.league_name})",
            f"Team B: {match.team_b.name} ({match.team_b.league_name})",
            f"Baslik: {match.title}",
            f"Motor: {ENGINE_MODE_VALUE_TO_LABEL.get(match.engine_mode, match.engine_mode)}",
        ]
        if match.engine_mode == "football_result_guided_test":
            guided_a = match.guided_target_score_a if match.guided_target_score_a is not None else 2
            guided_b = match.guided_target_score_b if match.guided_target_score_b is not None else 1
            info_lines.append(f"Guided Sonuc: {guided_a} - {guided_b}")
        self._set_selection_text("\n".join(info_lines))

    def _refresh_output_status(self) -> None:
        output_dir = CFG.base_dir / "output"
        if output_dir.exists():
            # En son _final.mp4 dosyasını bul, yoksa en son .mp4
            finals = sorted(output_dir.glob("*_final.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not finals:
                finals = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if finals:
                latest = finals[0]
                size_mb = latest.stat().st_size / (1024 * 1024)
                total = len(list(output_dir.glob("*_final.mp4"))) or len(list(output_dir.glob("*.mp4")))
                self._set_card_text(
                    self.output_card,
                    value_text=latest.name,
                    subtitle=f"{size_mb:.1f} MB  |  {total} video",
                )
                return

        self._set_card_text(
            self.output_card,
            value_text="Video yok",
            subtitle="Henuz export yapilmadi",
        )

    def _set_card_text(self, card: ctk.CTkFrame, value_text: str, subtitle: str) -> None:
        card._value_label.configure(text=value_text)  # type: ignore[attr-defined]
        card._subtitle_label.configure(text=subtitle)  # type: ignore[attr-defined]

    def _set_selection_text(self, text: str) -> None:
        self.last_selection_box.configure(state="normal")
        self.last_selection_box.delete("1.0", "end")
        self.last_selection_box.insert("1.0", text)
        self.last_selection_box.configure(state="disabled")

    def _create_status_card(
        self,
        parent,
        title: str,
        value_text: str,
        subtitle: str,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color="#0D1320")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#697A9B",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        value_label = ctk.CTkLabel(
            card,
            text=value_text,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F1F4FA",
            justify="left",
            wraplength=280,
        )
        value_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 4))

        subtitle_label = ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color="#5A6B8A",
            justify="left",
            wraplength=280,
        )
        subtitle_label.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 12))

        card._value_label = value_label  # type: ignore[attr-defined]
        card._subtitle_label = subtitle_label  # type: ignore[attr-defined]
        return card

    # --------------------------------------------------------
    # NAVIGASYON
    # --------------------------------------------------------
    def _go_to_team_tab(self) -> None:
        if not REPOSITORY.exists():
            messagebox.showerror(
                "Takim Havuzu Gerekli",
                "Once takim havuzunu guncellemelisin.",
            )
            return

        # Lig listelerini yenile
        REPOSITORY.load_teams(force_reload=True)
        self.team_a_panel.reload_leagues()
        self.team_b_panel.reload_leagues()

        # Mevcut secimi yukle
        match = REPOSITORY.load_selected_match()
        if match and not self.team_a_panel.selected_team and not self.team_b_panel.selected_team:
            self.team_a_panel.selected_team = match.team_a
            self.team_b_panel.selected_team = match.team_b
            self.real_fixture_var.set(match.is_real_fixture_reference)
            self._set_engine_mode_selection(match.engine_mode)
            if match.guided_target_score_a is not None:
                self.guided_score_a_var.set(str(match.guided_target_score_a))
            if match.guided_target_score_b is not None:
                self.guided_score_b_var.set(str(match.guided_target_score_b))
            self.team_a_panel._sync_selection_ui()
            self.team_b_panel._sync_selection_ui()

        self.tabview.set("Takim Secimi")

    # --------------------------------------------------------
    # PROCESS CALISTIRMA
    # --------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        state = "disabled" if busy else "normal"

        self.sync_button.configure(state=state)
        self.selector_button.configure(state=state)
        self.render_button.configure(state=state)
        self.ai_text_button.configure(state=state)
        self.refresh_button.configure(state=state)

    @staticmethod
    def _is_pop_engine_mode(engine_mode: str) -> bool:
        return engine_mode.startswith("pop_") or engine_mode == "pop_shift"

    def _canonical_engine_mode(self, engine_mode: str) -> str:
        canonical = ENGINE_MODE_ALIASES_TO_CANONICAL.get(engine_mode, engine_mode)
        if canonical in ENGINE_MODE_VALUE_TO_LABEL:
            return canonical
        return DEFAULT_ENGINE_MODE_VALUE

    def _set_engine_mode_selection(self, engine_mode: str) -> None:
        canonical = self._canonical_engine_mode((engine_mode or "").strip().lower())
        self.selected_engine_mode_value = canonical
        self._engine_mode_syncing = True
        try:
            self.football_mode_listbox.selection_clear(0, "end")
            self.pop_mode_listbox.selection_clear(0, "end")

            if self._is_pop_engine_mode(canonical):
                if canonical in self.pop_mode_values:
                    idx = self.pop_mode_values.index(canonical)
                    self.pop_mode_listbox.selection_set(idx)
                    self.pop_mode_listbox.see(idx)
            else:
                if canonical in self.football_mode_values:
                    idx = self.football_mode_values.index(canonical)
                    self.football_mode_listbox.selection_set(idx)
                    self.football_mode_listbox.see(idx)
        finally:
            self._engine_mode_syncing = False

        label = ENGINE_MODE_VALUE_TO_LABEL.get(canonical, canonical)
        self.engine_mode_status_label.configure(text=f"Aktif Motor: {label}")
        self._update_guided_inputs_state()

    def _is_guided_mode_selected(self) -> bool:
        return self.selected_engine_mode_value == "football_result_guided_test"

    def _update_guided_inputs_state(self) -> None:
        guided_enabled = self._is_guided_mode_selected()
        state = "normal" if guided_enabled else "disabled"
        self.guided_score_a_entry.configure(state=state)
        self.guided_score_b_entry.configure(state=state)
        label_color = "#D9E2F2" if guided_enabled else "#6E7F9F"
        self.guided_target_label.configure(text_color=label_color)

    def _handle_football_mode_select(self, _event=None) -> None:
        if self._engine_mode_syncing:
            return
        selection = self.football_mode_listbox.curselection()
        if not selection:
            return
        idx = int(selection[0])
        if 0 <= idx < len(self.football_mode_values):
            self._set_engine_mode_selection(self.football_mode_values[idx])
            self._refresh_match_summary()

    def _handle_pop_mode_select(self, _event=None) -> None:
        if self._engine_mode_syncing:
            return
        selection = self.pop_mode_listbox.curselection()
        if not selection:
            return
        idx = int(selection[0])
        if 0 <= idx < len(self.pop_mode_values):
            self._set_engine_mode_selection(self.pop_mode_values[idx])
            self._refresh_match_summary()

    def _run_python_script_async(
        self,
        script_name: str,
        success_message: str,
        refresh_after: bool = True,
        script_args: list[str] | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
        on_success: Callable[[], None] | None = None,
    ) -> None:
        if self.is_busy:
            self.log("Baska bir islem calisiyor. Once onun bitmesini bekle.")
            return

        script_path = BASE_DIR / script_name
        if not script_path.exists():
            messagebox.showerror("Dosya Yok", f"Bulunamadi:\n{script_path}")
            return

        self._set_busy(True)
        args = script_args or []
        display_command = " ".join([script_name, *args]).strip()
        self.log(f"Baslatiliyor: {display_command}")

        # Log sekmesine geç
        self.tabview.set("Islem Logu")

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    [sys.executable, "-u", str(script_path), *args],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                assert process.stdout is not None
                for line in process.stdout:
                    clean_line = line.rstrip()
                    self.after(0, self.log, clean_line)
                    if on_stdout_line is not None:
                        try:
                            on_stdout_line(clean_line)
                        except Exception as callback_exc:
                            self.after(0, self.log, f"Stdout callback hatasi: {callback_exc}")

                return_code = process.wait()

                if return_code == 0:
                    self.after(0, self.log, f"Tamamlandi: {script_name}")
                    if on_success is not None:
                        self.after(0, on_success)
                    self.after(
                        0,
                        lambda: messagebox.showinfo("Islem Tamamlandi", success_message),
                    )
                else:
                    self.after(0, self.log, f"Hata kodu: {return_code}")
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "Islem Basarisiz",
                            f"{script_name} calisirken hata olustu.\nLog sekmesini kontrol et.",
                        ),
                    )
            except Exception as exc:
                self.after(0, self.log, f"Beklenmeyen hata: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror("Beklenmeyen Hata", str(exc)),
                )
            finally:
                self.after(0, self._set_busy, False)
                if refresh_after:
                    self.after(0, self.refresh_status)

        threading.Thread(target=worker, daemon=True).start()

    # --------------------------------------------------------
    # BUTON AKSIYONLARI
    # --------------------------------------------------------
    def run_sync_teams(self) -> None:
        self._run_python_script_async(
            script_name="sync_teams.py",
            script_args=["--include-national-teams"],
            success_message="Takim havuzu (lig + milli) guncellendi.",
            refresh_after=True,
        )

    def run_video_render(self) -> None:
        if REPOSITORY.load_selected_match() is None:
            messagebox.showerror(
                "Secim Gerekli",
                "Once takim secim sekmesinden iki takim secip kaydetmelisin.",
            )
            return

        auto_context = self._capture_tournament_auto_context_for_render()
        render_result: dict | None = None

        def _on_stdout_line(line: str) -> None:
            nonlocal render_result
            parsed = self._parse_tournament_result_line(line)
            if parsed is not None:
                render_result = parsed

        def _on_success() -> None:
            self._try_auto_record_tournament_result(auto_context, render_result)

        self._run_python_script_async(
            script_name="main.py",
            success_message="Video export tamamlandi.",
            refresh_after=True,
            on_stdout_line=_on_stdout_line,
            on_success=_on_success,
        )

    def _run_full_tournament_mode(self, layout: str = "portrait_concat") -> None:
        tournament_id: str | None = None
        if self.current_tournament_state:
            tournament_id = str(self.current_tournament_state.get("id") or "")
        if not tournament_id:
            latest = TOURNAMENT_MANAGER.load_latest_tournament()
            if latest is None:
                messagebox.showerror("Turnuva Yok", "Full run icin once bir turnuva olustur veya yukle.")
                return
            tournament_id = str(latest.get("id") or "")
            self.current_tournament_state = latest

        if not tournament_id:
            messagebox.showerror("Turnuva Yok", "Gecerli turnuva id bulunamadi.")
            return

        def _on_success() -> None:
            updated = TOURNAMENT_MANAGER.load_tournament(tournament_id)
            if updated is not None:
                self.current_tournament_state = updated
                self._update_tournament_status_box()
                self._update_tournament_next_match_panel()
                self._render_tournament_bracket()

        self._run_python_script_async(
            script_name="run_tournament_full.py",
            success_message=(
                "Full turnuva run tamamlandi."
                if layout == "portrait_concat"
                else "Yatay yayin turnuva run tamamlandi."
            ),
            refresh_after=True,
            script_args=[
                "--tournament-id",
                tournament_id,
                "--layout",
                layout,
                "--replay-completed",
            ],
            on_success=_on_success,
        )

    def _capture_tournament_auto_context_for_render(self) -> dict | None:
        if not self.current_tournament_state:
            return None
        match_id = getattr(self, "_tournament_next_match_id", None)
        if not match_id:
            return None
        nxt = TOURNAMENT_MANAGER.get_next_match(self.current_tournament_state)
        if nxt is None:
            return None
        if str(nxt.get("id")) != str(match_id):
            return None
        return {
            "match_id": str(match_id),
            "team_a_key": str(nxt.get("team_a_key") or ""),
            "team_b_key": str(nxt.get("team_b_key") or ""),
        }

    def _parse_tournament_result_line(self, line: str) -> dict | None:
        marker = "TOURNAMENT_RESULT_JSON:"
        if not line.startswith(marker):
            return None
        raw = line[len(marker) :].strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _try_auto_record_tournament_result(self, context: dict | None, result: dict | None) -> None:
        if context is None:
            return
        if not self.current_tournament_state:
            self.log("Turnuva otomatik sonuc atlandi: aktif turnuva state bulunamadi.")
            return
        if result is None:
            self.log("Turnuva otomatik sonuc atlandi: render sonuc skoru okunamadi.")
            return

        match_id = str(context.get("match_id") or "")
        if not match_id:
            return

        result_team_a = str(result.get("team_a_key") or "")
        result_team_b = str(result.get("team_b_key") or "")
        expected_a = str(context.get("team_a_key") or "")
        expected_b = str(context.get("team_b_key") or "")
        if {result_team_a, result_team_b} != {expected_a, expected_b}:
            self.log("Turnuva otomatik sonuc atlandi: render edilen takimlar siradaki macla eslesmiyor.")
            return

        try:
            raw_score_a = int(result.get("score_a"))
            raw_score_b = int(result.get("score_b"))
        except Exception:
            self.log("Turnuva otomatik sonuc atlandi: skor parse edilemedi.")
            return

        if result_team_a == expected_a and result_team_b == expected_b:
            score_a, score_b = raw_score_a, raw_score_b
        elif result_team_a == expected_b and result_team_b == expected_a:
            score_a, score_b = raw_score_b, raw_score_a
        else:
            self.log("Turnuva otomatik sonuc atlandi: takim sirasi dogrulanamadi.")
            return

        try:
            state = TOURNAMENT_MANAGER.record_match_result_with_knockout_rules(
                state=self.current_tournament_state,
                match_id=match_id,
                score_a=score_a,
                score_b=score_b,
            )
        except Exception as exc:
            self.log(f"Turnuva otomatik sonuc islenemedi: {exc}")
            messagebox.showerror(
                "Turnuva Otomatik Isleme Hatasi",
                f"Render sonucu turnuvaya otomatik kaydedilemedi:\n{exc}",
            )
            return

        self.current_tournament_state = state
        self._update_tournament_status_box()
        self._update_tournament_next_match_panel()
        self._render_tournament_bracket()
        match_row = next((m for m in state.get("matches", []) if str(m.get("id")) == str(match_id)), None)
        decided_by = str((match_row or {}).get("decided_by") or "normal_time")
        final_a = int((match_row or {}).get("score_a") or score_a)
        final_b = int((match_row or {}).get("score_b") or score_b)
        self.log(
            f"Turnuva sonucu otomatik islendi: {score_a}-{score_b} -> {final_a}-{final_b} "
            f"({decided_by}, mac: {match_id})"
        )

    def open_output_location(self) -> None:
        output_dir = CFG.base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        # En son final videoyu seç
        finals = sorted(output_dir.glob("*_final.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if finals and sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(finals[0])])
        else:
            open_folder_in_explorer(output_dir)


    def restart_app(self) -> None:
        if self.is_busy:
            confirm = messagebox.askyesno(
                "Islem Devam Ediyor",
                "Arka planda calisan islem kapanacak.\nYine de uygulamayi yeniden baslatmak istiyor musun?",
            )
            if not confirm:
                return

        script_path = Path(sys.argv[0]).resolve()
        if not script_path.exists():
            script_path = BASE_DIR / "launcher_gui.py"

        try:
            self.log("Launcher yeniden baslatiliyor...")
            self.update_idletasks()
            os.execl(sys.executable, sys.executable, str(script_path), *sys.argv[1:])
        except Exception as exc:
            messagebox.showerror(
                "Yeniden Baslatma Hatasi",
                f"Uygulama yeniden baslatilamadi:\n{exc}",
            )
    # --------------------------------------------------------
    # AI METIN URETIMI
    # --------------------------------------------------------
    _AI_SYSTEM_PROMPT = (
        "You are a viral social media content strategist specializing in sports "
        "entertainment and SEO optimization.\n\n"
        "VIDEO CONCEPT:\n"
        "- A physics-based simulation decides the outcome of a football match\n"
        "- The result is determined purely by physics and luck\n"
        "- Short dramatic video (~55s): intro → live match → final result\n"
        "- Style: unpredictable, tense, football fan bait\n\n"
        "STRICT RULES:\n"
        "- NEVER reveal the score or winner — zero spoilers\n"
        "- English only, global audience\n"
        '- End every caption with a "who should play next?" question to drive comments\n'
        "- Every hashtag must be relevant — no filler tags\n"
        "- Follow each platform's character limits and best practices exactly\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1. YOUTUBE SHORTS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TITLE (max 100 chars, but front-load keywords in first 40 chars):\n"
        "- Start with team names or rivalry keyword for SEO\n"
        "- Create curiosity gap — no spoiler\n\n"
        "DESCRIPTION (max 5000 chars, use first 150 chars wisely — that's the visible preview):\n"
        "- Line 1: Hook with keywords (this is what Google indexes)\n"
        "- Line 2-3: Context about the matchup, build tension\n"
        '- Line 4: CTA → "Who should play next? Comment below!"\n'
        "- Line 5+: Hashtags + keyword-rich closing line\n\n"
        "HASHTAGS (put inside description, 3-5 max — YouTube penalizes tag spam):\n"
        "- Mix broad (#football #shorts) + niche (#[teamA]vs[teamB])\n\n"
        'TAGS (separate comma list for YouTube Studio "Tags" field, 8-12):\n'
        '- Long-tail keywords: "[Team A] vs [Team B]", "football simulation", '
        '"who wins", team names individually, league names\n\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "2. INSTAGRAM REELS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        'CAPTION (max 2200 chars, but only first 125 chars show before "...more"):\n'
        "- First 125 chars = scroll-stopping hook + team names (SEO critical)\n"
        "- Body: 2-3 short lines building suspense\n"
        '- CTA: "Which teams should go next? Drop it 👇"\n'
        "- Then a line break before hashtags\n\n"
        "HASHTAGS (after caption, 20-25):\n"
        "- Structure: 5 high-volume (1M+), 10 mid-volume (100K-1M), 5-10 niche (<100K)\n"
        "- Mix: football terms + satisfying content + team-specific + trending\n"
        "- Include both #[TeamA] and #[TeamB] as standalone tags\n\n"
        "ALT TEXT (max 100 chars — for accessibility + Instagram SEO):\n"
        '- Describe what\'s happening: "[Team A] vs [Team B] football simulation"\n\n'
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "3. TIKTOK\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "CAPTION (max 4000 chars, but only first 80-90 chars show on feed):\n"
        "- First 80 chars = the entire hook, must work standalone\n"
        "- Keep total caption under 150 chars for clean look\n"
        '- End with: "Next match? 👇"\n\n'
        "HASHTAGS (inline with caption, 4-6 max):\n"
        "- TikTok SEO = hashtags act as search keywords\n"
        "- Use 2 broad (#football #fyp) + 2-3 specific (#[teamA]vs[teamB])\n"
        "- Do NOT use #foryou or #foryoupage — TikTok confirmed they don't help"
    )

    def run_ai_text_generation(self) -> None:
        if self.is_busy:
            self.log("Baska bir islem calisiyor. Once onun bitmesini bekle.")
            return

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            messagebox.showerror(
                "API Anahtari Eksik",
                "OPENROUTER_API_KEY ortam degiskeni bulunamadi.\n"
                "Lutfen ortam degiskenlerini kontrol et.",
            )
            return

        match = REPOSITORY.load_selected_match()
        if match is None:
            messagebox.showerror(
                "Secim Gerekli",
                "Once takim secim sekmesinden iki takim secip kaydetmelisin.",
            )
            return

        self._set_busy(True)
        self.log("AI metin uretimi baslatiliyor...")

        user_message = (
            f"Match Info:\n"
            f"Team A: {match.team_a.name}\n"
            f"Team B: {match.team_b.name}\n"
            f"Please generate the content."
        )

        def worker() -> None:
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "google/gemini-2.5-flash",
                        "messages": [
                            {"role": "system", "content": self._AI_SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                self.after(0, self.log, "AI metin uretimi tamamlandi.")
                self.after(0, self.show_ai_results_window, content)
            except requests.exceptions.RequestException as exc:
                self.after(0, self.log, f"API hatasi: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror("API Hatasi", str(exc)),
                )
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                self.after(0, self.log, f"Yanit parse hatasi: {exc}")
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Yanit Hatasi",
                        f"API yanitindaki veri beklenmedik formatta:\n{exc}",
                    ),
                )
            finally:
                self.after(0, self._set_busy, False)

        threading.Thread(target=worker, daemon=True).start()

    def show_ai_results_window(self, raw_text: str) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Sosyal Medya Metinleri")
        win.geometry("1100x700")
        win.configure(fg_color="#0C111B")
        win.transient(self)

        # Parse sections
        sections = self._parse_ai_sections(raw_text)

        win.grid_columnconfigure((0, 1, 2), weight=1)
        win.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            win,
            text="Sosyal Medya Metinleri",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#F1F4FA",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 8))

        platform_configs = [
            ("YouTube Shorts", sections.get("youtube", "")),
            ("Instagram Reels", sections.get("instagram", "")),
            ("TikTok", sections.get("tiktok", "")),
        ]

        for col, (platform_name, text) in enumerate(platform_configs):
            frame = ctk.CTkFrame(win, corner_radius=14, fg_color="#0D1320")
            frame.grid(row=1, column=col, sticky="nsew", padx=(20 if col == 0 else 6, 20 if col == 2 else 6), pady=(0, 12))
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(1, weight=1)

            ctk.CTkLabel(
                frame,
                text=platform_name,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#EEF2FA",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

            textbox = ctk.CTkTextbox(
                frame,
                corner_radius=10,
                fg_color="#0A0F18",
                border_width=1,
                border_color="#243047",
                font=ctk.CTkFont(size=12),
                wrap="word",
            )
            textbox.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
            textbox.insert("1.0", text if text else raw_text)

            copy_btn = ctk.CTkButton(
                frame,
                text="Kopyala",
                height=34,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#7A3B99",
                hover_color="#5D2A75",
                command=lambda tb=textbox: self._copy_textbox_to_clipboard(tb),
            )
            copy_btn.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _parse_ai_sections(self, raw_text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        text_upper = raw_text.upper()

        # Try to find section markers
        yt_markers = ["1. YOUTUBE SHORTS", "1) YOUTUBE SHORTS", "YOUTUBE SHORTS"]
        ig_markers = ["2. INSTAGRAM REELS", "2) INSTAGRAM REELS", "INSTAGRAM REELS"]
        tt_markers = ["3. TIKTOK", "3) TIKTOK", "TIKTOK"]

        def find_marker(markers: list[str]) -> int:
            for m in markers:
                idx = text_upper.find(m)
                if idx != -1:
                    return idx
            return -1

        yt_idx = find_marker(yt_markers)
        ig_idx = find_marker(ig_markers)
        tt_idx = find_marker(tt_markers)

        indices = sorted(
            [(k, v) for k, v in [("youtube", yt_idx), ("instagram", ig_idx), ("tiktok", tt_idx)] if v != -1],
            key=lambda x: x[1],
        )

        if len(indices) < 2:
            return {}

        for i, (key, start) in enumerate(indices):
            end = indices[i + 1][1] if i + 1 < len(indices) else len(raw_text)
            sections[key] = raw_text[start:end].strip()

        return sections

    def _copy_textbox_to_clipboard(self, textbox: ctk.CTkTextbox) -> None:
        content = textbox.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(content)

    # --------------------------------------------------------
    # APP KAPANIRKEN
    # --------------------------------------------------------
    def destroy(self) -> None:
        if self.is_busy:
            confirm = messagebox.askyesno(
                "Islem Devam Ediyor",
                "Arka planda calisan bir islem var.\nYine de kapatmak istiyor musun?",
            )
            if not confirm:
                return
        super().destroy()


# ============================================================
# GIRIS NOKTASI
# ============================================================

def main() -> None:
    app = MarbleRaceLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
