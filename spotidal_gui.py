import tidalapi
import pandas as pd
import time
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import unicodedata
import re
from difflib import SequenceMatcher
import threading

# ---------------------------------------------------------
# 1. Hilfsfunktionen (Hybrid-Version + Sprache + Login-Fix)
# ---------------------------------------------------------

import unicodedata
import re
from difflib import SequenceMatcher

# Cache für schnellere Suche
SEARCH_CACHE = {}

# Sprachpakete für Block 1 (Suche + Login-Fix)
LANG = {
    "DE": {
        "normalize_warn": "Warnung: Text konnte nicht normalisiert werden.",
        "search_main": "Hauptsuche:",
        "search_fallback": "Fallback-Suche:",
        "search_no_results": "Keine Ergebnisse gefunden.",
        "search_best": "Bestes Ergebnis:",
        "login_fix": "Initialisiere TIDAL Session vollständig…"
    },
    "EN": {
        "normalize_warn": "Warning: Could not normalize text.",
        "search_main": "Main search:",
        "search_fallback": "Fallback search:",
        "search_no_results": "No results found.",
        "search_best": "Best match:",
        "login_fix": "Initializing TIDAL session fully…"
    }
}

# ---------------------------------------------------------
# Login-Fix: Session vollständig initialisieren
# ---------------------------------------------------------

def fix_tidal_session(session, language="DE"):
    """
    Initialisiert die TIDAL Session vollständig, damit nichts hängt.
    Sollte direkt nach erfolgreichem OAuth-Login aufgerufen werden.
    """
    L = LANG.get(language, LANG["DE"])

    try:
        print(L["login_fix"])
        session.user = tidalapi.User(session, session.user.id)
        session.load_user()
        session.country_code = session.user.country_code

        # Dummy-Call, damit die Session wirklich „wach“ ist
        _ = session.user.playlists()
    except Exception as e:
        print("Login-Fix Fehler:", e)

    return session

# ---------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------

def normalize(text):
    if not isinstance(text, str):
        return ""
    try:
        text = text.lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = re.sub(r"\(.*?\)", "", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except:
        print(LANG["DE"]["normalize_warn"])
        return ""

# ---------------------------------------------------------
# Fuzzy Matching
# ---------------------------------------------------------

def fuzzy_ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()

# ---------------------------------------------------------
# Track-Suche (zweisprachig)
# ---------------------------------------------------------

def search_track(session, title, artists, language="DE"):
    L = LANG.get(language, LANG["DE"])

    key = (title.lower(), artists.lower())
    if key in SEARCH_CACHE:
        return SEARCH_CACHE[key]

    title_norm = normalize(title)
    artists_norm = normalize(artists)

    # 1) Hauptsuche
    print(f"{L['search_main']} {title} – {artists}")
    try:
        result = session.search(query=f"{title} {artists}", models=[tidalapi.Track])
        tracks = result.get("tracks", [])
    except:
        tracks = []

    # 2) Fallback
    if not tracks:
        print(f"{L['search_fallback']} {title_norm} – {artists_norm}")
        try:
            result = session.search(query=f"{title_norm} {artists_norm}", models=[tidalapi.Track])
            tracks = result.get("tracks", [])
        except:
            SEARCH_CACHE[key] = None
            print(L["search_no_results"])
            return None

    # 3) Bestes Ergebnis bestimmen
    best = None
    best_score = 0

    for t in tracks[:5]:
        t_title = normalize(t.name)
        t_artists = normalize(" ".join(a.name for a in t.artists))

        score = (
            fuzzy_ratio(title_norm, t_title) * 0.7 +
            fuzzy_ratio(artists_norm, t_artists) * 0.3
        )

        if score > best_score:
            best_score = score
            best = t

    if best_score > 0.55:
        print(f"{L['search_best']} {best.name}")
        SEARCH_CACHE[key] = best
        return best

    print(L["search_no_results"])
    SEARCH_CACHE[key] = None
    return None

# ---------------------------------------------------------
# 2. GUI‑App (Dark Mode) + Sprache (OHNE LOGIN-GUI)
# ---------------------------------------------------------

class SpotidalGUI:
    def __init__(self, root):
        self.root = root
        root.title("Spotify → TIDAL Importer (Dark Mode)")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.geometry("750x720")

        # Abbruch-Flag
        self.stop_flag = False

        # Sprache
        self.language = "DE"

        # Sprachpakete
        self.lang = {
            "DE": {
                "lang_de": "🇩🇪 DE",
                "lang_en": "🇬🇧 EN",
                "csv": "CSV-Datei:",
                "choose": "Auswählen",
                "playlist": "Playlist-Name:",
                "default_playlist": "Spotify Favoriten (Import)",
                "start": "Import starten",
                "stop": "Abbrechen",
                "eta": "ETA",
                "percent": "0%"
            },
            "EN": {
                "lang_de": "🇩🇪 DE",
                "lang_en": "🇬🇧 EN",
                "csv": "CSV file:",
                "choose": "Browse",
                "playlist": "Playlist name:",
                "default_playlist": "Spotify Favorites (Import)",
                "start": "Start import",
                "stop": "Cancel",
                "eta": "ETA",
                "percent": "0%"
            }
        }

        # Farben
        bg = "#1e1e1e"
        fg = "#e0e0e0"
        entry_bg = "#2a2a2a"
        button_bg = "#333333"
        button_fg = "#ffffff"
        log_bg = "#111111"
        log_fg = "#d0d0d0"

        root.configure(bg=bg)

        # Styles
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", background=button_bg, foreground=button_fg, borderwidth=1)
        style.map("TButton", background=[("active", "#444444")])
        style.configure("TProgressbar", troughcolor="#2a2a2a", background="#4caf50")

        # ---------------------------------------------------------
        # Sprachauswahl
        # ---------------------------------------------------------

        lang_frame = tk.Frame(root, bg=bg)
        lang_frame.pack(anchor="ne", padx=10, pady=5)

        self.lang_de_btn = ttk.Button(lang_frame, text="🇩🇪 DE", width=6,
                                      command=lambda: self.set_language("DE"))
        self.lang_de_btn.pack(side="left", padx=3)

        self.lang_en_btn = ttk.Button(lang_frame, text="🇬🇧 EN", width=6,
                                      command=lambda: self.set_language("EN"))
        self.lang_en_btn.pack(side="left", padx=3)

        # ---------------------------------------------------------
        # CSV Auswahl
        # ---------------------------------------------------------

        self.csv_label = tk.Label(root, text=self.lang["DE"]["csv"], bg=bg, fg=fg)
        self.csv_label.pack(anchor="w", padx=10, pady=5)

        self.csv_path_var = tk.StringVar()
        self.csv_entry = tk.Entry(root, textvariable=self.csv_path_var,
                                  width=60, bg=entry_bg, fg=fg, insertbackground=fg)
        self.csv_entry.pack(anchor="w", padx=10)

        self.csv_button = ttk.Button(root, text=self.lang["DE"]["choose"], command=self.select_csv)
        self.csv_button.pack(anchor="w", padx=10, pady=5)

        # ---------------------------------------------------------
        # Playlist Name
        # ---------------------------------------------------------

        self.name_label = tk.Label(root, text=self.lang["DE"]["playlist"], bg=bg, fg=fg)
        self.name_label.pack(anchor="w", padx=10, pady=5)

        self.name_var = tk.StringVar(value=self.lang["DE"]["default_playlist"])
        self.name_entry = tk.Entry(root, textvariable=self.name_var,
                                   width=40, bg=entry_bg, fg=fg, insertbackground=fg)
        self.name_entry.pack(anchor="w", padx=10)

        # ---------------------------------------------------------
        # Fortschrittsbalken + Anzeigen
        # ---------------------------------------------------------

        self.progress = ttk.Progressbar(root, length=500, mode="determinate")
        self.progress.pack(pady=(10, 0))

        self.progress_label = tk.Label(root, text=self.lang["DE"]["percent"], bg=bg, fg=fg)
        self.progress_label.pack()

        self.eta_label = tk.Label(root, text=f"{self.lang['DE']['eta']}: --:--", bg=bg, fg=fg)
        self.eta_label.pack()

        # ---------------------------------------------------------
        # Log Fenster
        # ---------------------------------------------------------

        self.log = scrolledtext.ScrolledText(root, width=80, height=20,
                                             bg=log_bg, fg=log_fg,
                                             insertbackground=log_fg)
        self.log.pack(padx=10, pady=(10, 0), fill="both", expand=True)

        # ---------------------------------------------------------
        # Button-Leiste unten
        # ---------------------------------------------------------

        button_frame = tk.Frame(root, bg=bg)
        button_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        self.start_button = ttk.Button(button_frame, text=self.lang["DE"]["start"], command=self.start_import)
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(button_frame, text=self.lang["DE"]["stop"], command=self.stop_import)
        self.stop_button.pack(side="right")

    # ---------------------------------------------------------
    # Sprache ändern
    # ---------------------------------------------------------

    def set_language(self, lang):
        self.language = lang
        L = self.lang[lang]

        self.csv_label.config(text=L["csv"])
        self.csv_button.config(text=L["choose"])
        self.name_label.config(text=L["playlist"])
        self.name_var.set(L["default_playlist"])
        self.progress_label.config(text=L["percent"])
        self.eta_label.config(text=f"{L['eta']}: --:--")
        self.start_button.config(text=L["start"])
        self.stop_button.config(text=L["stop"])

    # ---------------------------------------------------------
    # Hilfsfunktionen GUI
    # ---------------------------------------------------------

    def log_write(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.root.update()

    def select_csv(self):
        path = filedialog.askopenfilename(
            title="CSV auswählen" if self.language == "DE" else "Select CSV",
            filetypes=[("CSV Dateien", "*.csv")] if self.language == "DE" else [("CSV files", "*.csv")]
        )
        if path:
            self.csv_path_var.set(path)

    def stop_import(self):
        self.stop_flag = True
        self.log_write("Abbruch angefordert…" if self.language == "DE" else "Cancel requested…")

    # ---------------------------------------------------------
    # Fenster schließen
    # ---------------------------------------------------------

    def on_close(self):
        self.stop_flag = True
        try:
            self.root.quit()
        except:
            pass
        self.root.destroy()


    # ---------------------------------------------------------
    # 3. THREADING + IMPORT-LOGIK (MIT LOGIN-FLOW, OHNE LOGIN-GUI)
    # ---------------------------------------------------------

    def start_import(self):
        self.stop_flag = False
        thread = threading.Thread(target=self._run_import, daemon=True)
        thread.start()

    def _run_import(self):

        L = {
            "DE": {
                "csv_missing": "Bitte eine CSV-Datei auswählen.",
                "csv_bad": "CSV konnte nicht geladen werden:",
                "csv_cols": "CSV hat nicht die erwarteten Spalten.",
                "login_start": "Starte TIDAL Login…",
                "login_browser": "Öffne Browser für TIDAL Login…",
                "login_code": "Bitte Login im Browser abschließen. Code:",
                "login_ok": "Erfolgreich bei TIDAL angemeldet.",
                "playlist_create": "Erstelle Playlist:",
                "search": "Suche:",
                "found": "✓ Gefunden:",
                "not_found": "✗ Nicht gefunden",
                "stats": "===== Statistik =====",
                "stats_found": "Gefunden:",
                "stats_not_found": "Nicht gefunden:",
                "stats_nf_list": "Nicht gefundene Titel:",
                "done": "Fertig!",
                "popup_done": "Playlist wurde erfolgreich importiert!"
            },
            "EN": {
                "csv_missing": "Please select a CSV file.",
                "csv_bad": "CSV could not be loaded:",
                "csv_cols": "CSV does not contain the expected columns.",
                "login_start": "Starting TIDAL login…",
                "login_browser": "Opening browser for TIDAL login…",
                "login_code": "Please complete login in browser. Code:",
                "login_ok": "Successfully logged in to TIDAL.",
                "playlist_create": "Creating playlist:",
                "search": "Searching:",
                "found": "✓ Found:",
                "not_found": "✗ Not found",
                "stats": "===== Statistics =====",
                "stats_found": "Found:",
                "stats_not_found": "Not found:",
                "stats_nf_list": "Tracks not found:",
                "done": "Done!",
                "popup_done": "Playlist imported successfully!"
            }
        }[self.language]

        # ---------------------------------------------------------
        # 1) LOGIN-FLOW (Browser + Code)
        # ---------------------------------------------------------
        self.log_write(L["login_start"])

        session = tidalapi.Session()
        login, future = session.login_oauth()

        self.log_write(L["login_browser"])

        import subprocess, os, webbrowser

        url = login.verification_uri_complete
        if not url.startswith("http"):
            url = "https://" + url

        try:
            webbrowser.open(url)
        except:
            try:
                os.startfile(url)
            except:
                subprocess.Popen(["cmd", "/c", "start", "", url], shell=True)

        self.log_write(f"{L['login_code']} {login.user_code}")

        try:
            future.result(timeout=180)
        except Exception as e:
            self.log_write(f"Login Timeout: {e}")
            return

        self.log_write(L["login_ok"])


        # ---------------------------------------------------------
        # 2) CSV prüfen
        # ---------------------------------------------------------
        csv_path = self.csv_path_var.get()
        playlist_name = self.name_var.get()

        if not csv_path:
            messagebox.showerror("Fehler" if self.language=="DE" else "Error",
                                 L["csv_missing"])
            return

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            messagebox.showerror("Fehler" if self.language=="DE" else "Error",
                                 f"{L['csv_bad']}\n{e}")
            return

        if "Track Name" not in df.columns or "Artist Name(s)" not in df.columns:
            messagebox.showerror("Fehler" if self.language=="DE" else "Error",
                                 L["csv_cols"])
            return

        # ---------------------------------------------------------
        # 3) Playlist erstellen
        # ---------------------------------------------------------
        self.log_write(f"{L['playlist_create']} {playlist_name}")
        playlist = session.user.create_playlist(playlist_name, "Import")
        self.log_write(f"Playlist-ID: {playlist.id}")

        tidal_ids = []
        not_found = []

        total = len(df)
        self.progress["maximum"] = 100
        start_time = time.time()

        # ---------------------------------------------------------
        # 4) TRACK-SUCHE
        # ---------------------------------------------------------
        for idx, row in df.iterrows():

            if self.stop_flag:
                self.log_write("Import abgebrochen.")
                return

            title = str(row["Track Name"])
            artists = str(row["Artist Name(s)"])

            self.log_write(f"[{idx+1}/{total}] {L['search']} {title} – {artists}")

            track = search_track(session, title, artists, self.language)

            if track:
                self.log_write(
                    f"  {L['found']} {track.name} – {', '.join(a.name for a in track.artists)}"
                )
                tidal_ids.append(track.id)
            else:
                self.log_write(f"  {L['not_found']}")
                not_found.append((title, artists))

            percent = int(((idx + 1) / total) * 100)
            self.progress["value"] = percent
            self.progress_label.config(text=f"{percent}%")

            elapsed = time.time() - start_time
            avg = elapsed / (idx + 1)
            remaining = avg * (total - (idx + 1))
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            self.eta_label.config(text=f"ETA: {mins:02d}:{secs:02d}")

            self.root.update_idletasks()

        # ---------------------------------------------------------
        # 5) Tracks hinzufügen
        # ---------------------------------------------------------
        chunk_size = 50
        for i in range(0, len(tidal_ids), chunk_size):
            playlist.add(tidal_ids[i:i+chunk_size])
            self.log_write(f"  Hinzugefügt: {i+1}–{i+len(tidal_ids[i:i+chunk_size])}")

        # ---------------------------------------------------------
        # 6) Statistik
        # ---------------------------------------------------------
        self.log_write("")
        self.log_write(L["stats"])
        self.log_write(f"{L['stats_found']} {len(tidal_ids)}")
        self.log_write(f"{L['stats_not_found']} {len(not_found)}")
        self.log_write("=====================")
        self.log_write("")

        if not_found:
            self.log_write(L["stats_nf_list"])
            for t, a in not_found:
                self.log_write(f"- {t} – {a}")

        self.log_write(L["done"])
        messagebox.showinfo("OK", L["popup_done"])


# ---------------------------------------------------------
# 4. Start
# ---------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = SpotidalGUI(root)
    root.mainloop()
