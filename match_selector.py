from __future__ import annotations

from pathlib import Path
from tkinter import Listbox, Scrollbar, StringVar, Tk, messagebox

import customtkinter as ctk

from config import build_default_config
from models import MatchSelection, TeamRecord
from team_repository import TeamRepository


APP_WIDTH = 1100
APP_HEIGHT = 680

CFG = build_default_config()
REPOSITORY = TeamRepository(CFG.data_dir)


class TeamPickerPanel(ctk.CTkFrame):
    def __init__(self, master, title: str, repository: TeamRepository) -> None:
        super().__init__(master, corner_radius=18, fg_color="#101726")
        self.repository = repository
        self.selected_team: TeamRecord | None = None
        self.filtered_teams: list[TeamRecord] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color="#EEF2FA",
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.league_var = StringVar(value="All Leagues")
        self.league_menu = ctk.CTkOptionMenu(
            self,
            values=self.repository.get_league_names(),
            variable=self.league_var,
            command=lambda _value: self.refresh_team_list(),
        )
        self.league_menu.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            self,
            placeholder_text="Takim ara...",
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda _event: self.refresh_team_list())

        list_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#0A111D")
        list_frame.grid(row=4, column=0, sticky="nsew", padx=18, pady=(0, 12))
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
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.listbox.bind("<<ListboxSelect>>", self._handle_listbox_select)

        scrollbar = Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.selection_label = ctk.CTkLabel(
            self,
            text="Secili takim: -",
            justify="left",
            font=ctk.CTkFont(size=13),
            text_color="#AAB5CA",
        )
        self.selection_label.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))

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

        self.selected_team = next((team for team in self.filtered_teams if team.team_key == current_key), None)
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
                f"Secili takim: {self.selected_team.name}\n"
                f"Lig: {self.selected_team.league_name}\n"
                f"Kisa ad: {self.selected_team.short_name}"
            )
        )

        try:
            index = next(
                idx for idx, team in enumerate(self.filtered_teams) if team.team_key == self.selected_team.team_key
            )
        except StopIteration:
            return

        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)


class MatchSelectorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Takim Secimi")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(980, 620)
        self.configure(fg_color="#09111D")

        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_panels()
        self._build_footer()
        self._load_existing_selection()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=18, fg_color="#101726")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Football Marble Race Match Selector",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#EEF2FA",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))

        ctk.CTkLabel(
            header,
            text="Iki takimi sec. Video basligi otomatik olarak sadece takim isimlerinden olusur.",
            font=ctk.CTkFont(size=14),
            text_color="#A8B3C9",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))

    def _build_panels(self) -> None:
        self.team_a_panel = TeamPickerPanel(self, "Team A", REPOSITORY)
        self.team_a_panel.grid(row=1, column=0, sticky="nsew", padx=(18, 9), pady=(0, 12))

        self.team_b_panel = TeamPickerPanel(self, "Team B", REPOSITORY)
        self.team_b_panel.grid(row=1, column=1, sticky="nsew", padx=(9, 18), pady=(0, 12))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, corner_radius=18, fg_color="#101726")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)

        self.auto_title_label = ctk.CTkLabel(
            footer,
            text="Video basligi: Takim secildiginde otomatik olusur",
            justify="left",
            text_color="#D9E2F2",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.auto_title_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))

        self.real_fixture_var = ctk.BooleanVar(value=False)
        self.real_fixture_checkbox = ctk.CTkCheckBox(
            footer,
            text="Bu eslesme gercek mac referansi",
            variable=self.real_fixture_var,
        )
        self.real_fixture_checkbox.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 8))

        self.summary_label = ctk.CTkLabel(
            footer,
            text="Kaydedilecek secim: -",
            justify="left",
            text_color="#A8B3C9",
            font=ctk.CTkFont(size=13),
        )
        self.summary_label.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))

        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            actions,
            text="Secimi Yenile",
            command=self._refresh_summary,
            fg_color="#3E4C66",
            hover_color="#2E3A51",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            actions,
            text="Secimi Kaydet",
            command=self._save_selection,
            fg_color="#1C7B59",
            hover_color="#165E45",
        ).grid(row=0, column=1, sticky="ew", padx=6)

        ctk.CTkButton(
            actions,
            text="Kapat",
            command=self.destroy,
            fg_color="#92404A",
            hover_color="#733039",
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.after(300, self._attach_periodic_summary_refresh)

    def _attach_periodic_summary_refresh(self) -> None:
        self._refresh_summary()
        self.after(700, self._attach_periodic_summary_refresh)

    def _load_existing_selection(self) -> None:
        selection = REPOSITORY.load_selected_match()
        if selection is None:
            self._refresh_summary()
            return

        self.real_fixture_var.set(selection.is_real_fixture_reference)
        self.team_a_panel.selected_team = selection.team_a
        self.team_b_panel.selected_team = selection.team_b
        self.team_a_panel._sync_selection_ui()
        self.team_b_panel._sync_selection_ui()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        team_a = self.team_a_panel.selected_team
        team_b = self.team_b_panel.selected_team

        if not team_a or not team_b:
            self.auto_title_label.configure(text="Video basligi: Takim secildiginde otomatik olusur")
            self.summary_label.configure(text="Kaydedilecek secim: Iki takimi da secmelisin.")
            return

        title = f"{team_a.name} vs {team_b.name}"
        fixture_text = "Evet" if self.real_fixture_var.get() else "Hayir"
        self.auto_title_label.configure(text=f"Video basligi: {title}")
        self.summary_label.configure(
            text=(
                f"Kaydedilecek secim:\n"
                f"Team A: {team_a.name} ({team_a.league_name})\n"
                f"Team B: {team_b.name} ({team_b.league_name})\n"
                f"Baslik: {title}\n"
                f"Gercek mac referansi: {fixture_text}"
            )
        )

    def _save_selection(self) -> None:
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
        self._refresh_summary()
        messagebox.showinfo("Kaydedildi", f"Eslesme basariyla kaydedildi:\n{output_path}")


def main() -> None:
    if not REPOSITORY.exists():
        root = Tk()
        root.withdraw()
        messagebox.showerror(
            "Takim Havuzu Yok",
            "Once sync_teams.py ile takim havuzunu olusturmalisin.",
        )
        root.destroy()
        return

    app = MatchSelectorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
