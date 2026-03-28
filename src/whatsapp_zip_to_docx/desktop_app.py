from __future__ import annotations

from pathlib import Path
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app_launcher import open_assistant_state, run_document_session
from .app_model import AssistantState
from .google_drive import DriveConfig

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
except ImportError:
    DND_FILES = None
    TkinterDnD = None


class DesktopApp:
    def __init__(self) -> None:
        self.dnd_enabled = False
        if TkinterDnD is not None:
            try:
                self.root = TkinterDnD.Tk()
                self.dnd_enabled = True
            except RuntimeError:
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()
        self.root.title("WhatsApp Zip to Word")
        self.root.geometry("860x680")

        self.state: AssistantState | None = None
        self.participant_vars: dict[str, tk.StringVar] = {}
        self.participant_entries: list[tk.Entry] = []
        self.profile_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.output_summary_var = tk.StringVar(value="Aucun document de sortie sélectionné.")
        self.status_var = tk.StringVar(value="Déposez bientôt un zip ici. Pour l’instant, utilisez le bouton d’ouverture.")
        self._generation_running = False
        self._generation_started_at = 0.0
        self._generation_context = ""

        self._build_ui()

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="WhatsApp Zip to Word", font=("Helvetica", 20, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Assistant macOS pour préparer et générer un document Word à partir d’un export WhatsApp.",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 0))

        drop_frame = ttk.LabelFrame(self.root, text="Import", padding=16)
        drop_frame.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")
        drop_frame.columnconfigure(0, weight=1)

        drop_hint = ttk.Label(
            drop_frame,
            text=self._drop_hint_text(),
            justify="center",
            anchor="center",
        )
        drop_hint.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.drop_hint = drop_hint

        open_button = ttk.Button(drop_frame, text="Ouvrir un zip…", command=self._open_zip)
        open_button.grid(row=1, column=0)

        if self.dnd_enabled and DND_FILES is not None:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            drop_hint.drop_target_register(DND_FILES)
            drop_hint.dnd_bind("<<Drop>>", self._on_drop)

        config_frame = ttk.LabelFrame(self.root, text="Assistant", padding=16)
        config_frame.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Profil").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.profile_combo = ttk.Combobox(config_frame, textvariable=self.profile_var, state="readonly")
        self.profile_combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_changed)

        ttk.Label(config_frame, text="Document Word").grid(row=1, column=0, sticky="w", pady=(0, 8))
        output_row = ttk.Frame(config_frame)
        output_row.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        output_row.columnconfigure(0, weight=1)
        self.output_entry = tk.Entry(output_row, textvariable=self.output_var, relief="solid", borderwidth=1)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Choisir…", command=self._choose_output).grid(row=0, column=1, padx=(8, 0))
        self.output_summary_label = tk.Label(
            config_frame,
            textvariable=self.output_summary_var,
            fg="#555555",
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.output_summary_label.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        inline_actions = ttk.Frame(config_frame)
        inline_actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        inline_actions.columnconfigure(0, weight=1)
        ttk.Label(inline_actions, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.generate_button = ttk.Button(inline_actions, text="Générer le document", command=self._generate)
        self.generate_button.grid(row=0, column=1, sticky="e")
        self.generate_button.state(["disabled"])

        self.participants_frame = ttk.LabelFrame(config_frame, text="Participants")
        self.participants_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.participants_frame.columnconfigure(0, weight=1)
        self.participants_frame.rowconfigure(0, weight=1)

        self.participants_canvas = tk.Canvas(self.participants_frame, height=280, highlightthickness=0)
        self.participants_canvas.grid(row=0, column=0, sticky="nsew")
        participants_scrollbar = ttk.Scrollbar(
            self.participants_frame,
            orient="vertical",
            command=self.participants_canvas.yview,
        )
        participants_scrollbar.grid(row=0, column=1, sticky="ns")
        self.participants_canvas.configure(yscrollcommand=participants_scrollbar.set)

        self.participants_inner = ttk.Frame(self.participants_canvas)
        self.participants_inner.columnconfigure(1, weight=1)
        self.participants_canvas_window = self.participants_canvas.create_window(
            (0, 0),
            window=self.participants_inner,
            anchor="nw",
        )
        self.participants_inner.bind("<Configure>", self._on_participants_configure)
        self.participants_canvas.bind("<Configure>", self._on_participants_canvas_configure)
        self.participants_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        log_frame = ttk.LabelFrame(self.root, text="Journal", padding=16)
        log_frame.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=14)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.insert("1.0", "Le document généré et les avertissements apparaîtront ici.\n")
        self.log_text.configure(state="disabled")

    def _open_zip(self) -> None:
        path = filedialog.askopenfilename(
            title="Choisir un export WhatsApp",
            parent=self.root,
            filetypes=[("WhatsApp Zip", "*.zip"), ("All files", "*.*")],
        )
        if not path:
            return
        self._load_zip(Path(path))

    def _load_zip(self, zip_path: Path) -> None:
        try:
            state = open_assistant_state(zip_path)
        except Exception as exc:
            messagebox.showerror("Ouverture impossible", str(exc))
            return

        self.state = state
        self.profile_var.set(state.selected_profile_name)
        self.profile_combo["values"] = state.available_profile_names
        self._set_output_path(str(state.output_docx))
        self._render_participants(state)
        self.generate_button.state(["!disabled"])
        self.status_var.set(f"Zip chargé : {zip_path.name}")
        self._append_log(f"Session ouverte pour {zip_path.name}")

    def _on_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return
        first = Path(paths[0])
        if first.suffix.lower() != ".zip":
            messagebox.showerror("Format non supporté", "Déposez un export WhatsApp au format .zip.")
            return
        self._load_zip(first)

    def _choose_output(self) -> None:
        if self.state is None:
            return
        path = filedialog.asksaveasfilename(
            title="Choisir le document Word",
            parent=self.root,
            defaultextension=".docx",
            filetypes=[("Word document", "*.docx")],
            initialdir=str(Path(self.output_var.get()).parent) if self.output_var.get().strip() else None,
            initialfile=Path(self.output_var.get()).name if self.output_var.get().strip() else "output.docx",
        )
        if not path:
            return
        if not path.lower().endswith(".docx"):
            path = f"{path}.docx"
        self._set_output_path(path)
        self.state = self.state.with_output_docx(Path(path))
        self.status_var.set("Document Word sélectionné.")
        self._append_log(f"Document de sortie choisi : {path}")

    def _on_profile_changed(self, _event=None) -> None:
        if self.state is None:
            return
        profile_name = self.profile_var.get()
        if not profile_name:
            return
        self.state = self.state.with_profile(profile_name)
        self._append_log(f"Profil sélectionné : {profile_name}")

    def _render_participants(self, state: AssistantState) -> None:
        for child in self.participants_inner.winfo_children():
            child.destroy()
        self.participant_vars.clear()
        self.participant_entries.clear()

        for row, participant in enumerate(state.participants):
            ttk.Label(self.participants_inner, text=participant.author_name).grid(row=row, column=0, sticky="w", padx=8, pady=6)
            var = tk.StringVar(value=participant.initial)
            self.participant_vars[participant.author_name] = var
            entry = tk.Entry(self.participants_inner, textvariable=var, width=12, relief="solid", borderwidth=1)
            entry.grid(row=row, column=1, sticky="w", padx=8, pady=6)
            self.participant_entries.append(entry)
        self.root.after(10, self._refresh_participants_scrollregion)

    def _collect_state(self) -> AssistantState:
        assert self.state is not None
        output_value = self.output_var.get().strip()
        if not output_value:
            output_value = str(self.state.output_docx)
            self._set_output_path(output_value)
        state = self.state.with_output_docx(Path(output_value))
        if self.profile_var.get():
            state = state.with_profile(self.profile_var.get())
        for author_name, var in self.participant_vars.items():
            state = state.with_participant_initial(author_name, var.get())
        return state

    def _generate(self) -> None:
        if self.state is None:
            return
        state = self._collect_state()
        unique_urls = len({url for message in state.session.conversation.messages for url in message.urls})
        video_count = sum(
            1
            for message in state.session.conversation.messages
            if message.attachment and message.attachment.path.suffix.lower() in {".mp4", ".mov", ".m4v"}
        )
        self.generate_button.state(["disabled"])
        context_bits: list[str] = []
        if unique_urls:
            context_bits.append(f"{unique_urls} liens")
        if state.selected_profile.video_mode == "drive" and video_count:
            context_bits.append(f"{video_count} vidéos Google Drive")
        self._generation_context = ", ".join(context_bits)
        self._generation_running = True
        self._generation_started_at = time.monotonic()
        self._refresh_generation_status()
        self._append_log("Lancement de la génération…")
        if unique_urls or video_count:
            self._append_log(
                "Préparation : "
                + ", ".join(
                    bit
                    for bit in [
                        f"{unique_urls} lien(s) à analyser" if unique_urls else "",
                        f"{video_count} vidéo(s) à traiter" if video_count else "",
                    ]
                    if bit
                )
                + "."
            )

        thread = threading.Thread(target=self._generate_worker, args=(state,), daemon=True)
        thread.start()

    def _generate_worker(self, state: AssistantState) -> None:
        try:
            drive_config = DriveConfig(
                credentials_path=Path("secrets/client_secret_819489726933-ku0rotlcdumi2nphpfoqquun51krl2ah.apps.googleusercontent.com.json"),
                token_path=Path("secrets/google_drive_token.json"),
            )
            result = run_document_session(state.session.with_profile(state.selected_profile_name).with_output(state.output_docx), initials_by_author={
                participant.author_name: participant.initial for participant in state.participants
            }, drive_config=drive_config)
        except Exception as exc:
            details = traceback.format_exc()
            self.root.after(0, lambda exc=exc, details=details: self._generation_failed(exc, details))
            return
        self.root.after(0, lambda state=state, result=result: self._generation_succeeded(state, result))

    def _generation_succeeded(self, state: AssistantState, result: EngineResult) -> None:
        self.state = state
        self._generation_running = False
        self.generate_button.state(["!disabled"])
        self.status_var.set("Document généré.")
        self._append_log(f"Document généré : {result.output_docx}")
        for warning in result.warnings:
            self._append_log(f"Avertissement [{warning.code}] : {warning.message}")
        for line in result.logs:
            self._append_log(line)
        messagebox.showinfo("Génération terminée", f"Document généré :\n{result.output_docx}")

    def _generation_failed(self, exc: Exception, details: str | None = None) -> None:
        self._generation_running = False
        self.generate_button.state(["!disabled"])
        self.status_var.set("Échec de génération.")
        self._append_log(f"Erreur : {exc}")
        if details:
            self._append_log(details.rstrip())
        messagebox.showerror("Génération impossible", str(exc))

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_output_path(self, path: str) -> None:
        self.output_var.set(path)
        self.output_summary_var.set(f"Fichier de sortie : {path}")
        if hasattr(self, "output_entry") and self.output_entry.winfo_exists():
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)
            self.output_entry.xview_moveto(1.0)
        self.root.update_idletasks()

    def _on_participants_configure(self, _event=None) -> None:
        self._refresh_participants_scrollregion()

    def _on_participants_canvas_configure(self, event) -> None:
        self.participants_canvas.itemconfigure(self.participants_canvas_window, width=event.width)

    def _refresh_participants_scrollregion(self) -> None:
        self.participants_canvas.configure(scrollregion=self.participants_canvas.bbox("all"))

    def _on_mousewheel(self, event) -> None:
        if self.participants_canvas.winfo_exists():
            self.participants_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _drop_hint_text(self) -> str:
        if self.dnd_enabled:
            return "Déposez un zip WhatsApp ici, ou utilisez “Ouvrir un zip…”."
        return "Le glisser-déposer sera actif dès que la dépendance GUI sera installée.\nEn attendant, utilisez “Ouvrir un zip…”."

    def _refresh_generation_status(self) -> None:
        if not self._generation_running:
            return
        elapsed = int(time.monotonic() - self._generation_started_at)
        if self._generation_context:
            self.status_var.set(f"Génération en cours… {self._generation_context} ({elapsed}s)")
        else:
            self.status_var.set(f"Génération en cours… ({elapsed}s)")
        self.root.after(1000, self._refresh_generation_status)


def run_desktop_app() -> None:
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    run_desktop_app()
