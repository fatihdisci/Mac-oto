# launcher_gui.py
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Listbox, Scrollbar, StringVar, messagebox

import customtkinter as ctk

from config import build_default_config
from models import MatchSelection, TeamRecord
from team_repository import TeamRepository


# ============================================================
# GENEL SABITLER
# ============================================================

APP_WIDTH = 1280
APP_HEIGHT = 860

BASE_DIR = Path(__file__).resolve().parent
CFG = build_default_config()
REPOSITORY = TeamRepository(CFG.data_dir)


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
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(1100, 750)
        self.configure(fg_color="#0C111B")

        self.is_busy = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabs()

        self.refresh_status()

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
        self.tab_log = self.tabview.add("Islem Logu")

        self._build_main_tab()
        self._build_teams_tab()
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
        self.render_button.pack(fill="x", pady=(8, 12))

        ctk.CTkLabel(
            left,
            text=(
                "Onerilen sira:\n"
                "1. Takim havuzunu guncelle\n"
                "2. Takim Secimi sekmesine git\n"
                "3. Iki takimi sec ve kaydet\n"
                "4. Videoyu uret"
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

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        btn_row.grid_columnconfigure((0, 1), weight=1)

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
            text="Ana Panele Don",
            height=42,
            font=ctk.CTkFont(size=14),
            fg_color="#3E4C66",
            hover_color="#2E3A51",
            command=lambda: self.tabview.set("Ana Panel"),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # Periyodik ozet
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
        self.match_summary_label.configure(
            text=f"Video basligi:  {title}",
            text_color="#D9E2F2",
        )

    def _save_team_selection(self) -> None:
        team_a = self.team_a_panel.selected_team
        team_b = self.team_b_panel.selected_team

        if not team_a or not team_b:
            messagebox.showerror("Eksik Secim", "Team A ve Team B secilmeden kayit yapilamaz.")
            return

        if team_a.team_key == team_b.team_key:
            messagebox.showerror("Gecersiz Eslesme", "Ayni takim iki tarafa birden secilemez.")
            return

        title = f"{team_a.name} vs {team_b.name}"
        selection = MatchSelection(
            team_a=team_a,
            team_b=team_b,
            title=title,
            is_real_fixture_reference=self.real_fixture_var.get(),
        )

        output_path = REPOSITORY.save_selected_match(selection)
        self.refresh_status()
        messagebox.showinfo("Kaydedildi", f"Eslesme kaydedildi:\n{title}\n\n{output_path}")

    # --------------------------------------------------------
    # TAB 3: ISLEM LOGU
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
        ]
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
        self.refresh_button.configure(state=state)

    def _run_python_script_async(
        self,
        script_name: str,
        success_message: str,
        refresh_after: bool = True,
        script_args: list[str] | None = None,
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
                    self.after(0, self.log, line.rstrip())

                return_code = process.wait()

                if return_code == 0:
                    self.after(0, self.log, f"Tamamlandi: {script_name}")
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

        self._run_python_script_async(
            script_name="main.py",
            success_message="Video export tamamlandi.",
            refresh_after=True,
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
