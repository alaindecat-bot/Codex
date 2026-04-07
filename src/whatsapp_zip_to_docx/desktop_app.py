from __future__ import annotations

from pathlib import Path
import multiprocessing as mp
import queue
import subprocess
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app_launcher import open_assistant_state
from .app_model import AssistantState
from .engine import EngineRequest, EngineResult
from .google_drive import DriveConfig
from .orchestrator import generate_document
from .timing_estimator import (
    TimingPrediction,
    append_timing_history,
    comparison_for_interrupted_run,
    comparison_from_performance_report,
    make_history_entry,
    write_prediction_comparison,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
except ImportError:
    DND_FILES = None
    TkinterDnD = None


def _generation_process_main(
    request: EngineRequest,
    drive_config: DriveConfig,
    result_queue,
) -> None:
    try:
        result = generate_document(request, drive_config=drive_config)
    except Exception as exc:  # pragma: no cover - executed in child process
        result_queue.put(
            {
                "status": "error",
                "message": str(exc),
                "details": traceback.format_exc(),
            }
        )
        return
    result_queue.put({"status": "success", "result": result})


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
        self.root.geometry("980x860")

        self.state: AssistantState | None = None
        self.participant_vars: dict[str, tk.StringVar] = {}
        self.participant_entries: list[tk.Entry] = []
        self.profile_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.output_summary_var = tk.StringVar(value="Aucun document de sortie sélectionné.")
        self.status_var = tk.StringVar(value="Déposez bientôt un zip ici. Pour l’instant, utilisez le bouton d’ouverture.")
        self.prediction_var = tk.StringVar(value="Chargez un ZIP pour obtenir une estimation.")
        self.progress_detail_var = tk.StringVar(value="Aucune génération en cours.")
        self.performance_report_var = tk.BooleanVar(value=True)
        self.timeout_mode_var = tk.StringVar(value="multiplier")
        self.timeout_multiplier_var = tk.StringVar(value="2.0")
        self.timeout_fixed_minutes_var = tk.StringVar(value="15")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._generation_running = False
        self._generation_started_at = 0.0
        self._generation_context = ""
        self._generation_process: mp.Process | None = None
        self._generation_queue = None
        self._current_prediction: TimingPrediction | None = None
        self._current_timeout_seconds = 0.0
        self._current_state: AssistantState | None = None
        self._analysis_path: Path | None = None
        self._performance_dashboard_path: Path | None = None
        self._performance_report_path: Path | None = None

        self._build_ui()

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="WhatsApp Zip to Word", font=("Helvetica", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Assistant macOS pour préparer, estimer et générer un document Word à partir d’un export WhatsApp.",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        drop_frame = ttk.LabelFrame(self.root, text="Import", padding=16)
        drop_frame.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")
        drop_frame.columnconfigure(0, weight=1)

        self.drop_hint = ttk.Label(drop_frame, text=self._drop_hint_text(), justify="center", anchor="center")
        self.drop_hint.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Button(drop_frame, text="Ouvrir un zip…", command=self._open_zip).grid(row=1, column=0)

        if self.dnd_enabled and DND_FILES is not None:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_hint.drop_target_register(DND_FILES)
            self.drop_hint.dnd_bind("<<Drop>>", self._on_drop)

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
            wraplength=780,
        )
        self.output_summary_label.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        options_frame = ttk.LabelFrame(config_frame, text="Execution", padding=12)
        options_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        ttk.Checkbutton(
            options_frame,
            text="Rapport de performance",
            variable=self.performance_report_var,
            command=self._on_execution_option_changed,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        ttk.Label(options_frame, text="Timeout").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            options_frame,
            text="x durée prévue",
            variable=self.timeout_mode_var,
            value="multiplier",
            command=self._on_execution_option_changed,
        ).grid(row=0, column=2, sticky="w")
        multiplier_entry = tk.Entry(options_frame, textvariable=self.timeout_multiplier_var, width=6, relief="solid", borderwidth=1)
        multiplier_entry.grid(row=0, column=3, sticky="w", padx=(6, 16))
        multiplier_entry.bind("<FocusOut>", lambda _event: self._on_execution_option_changed())

        ttk.Radiobutton(
            options_frame,
            text="minutes fixes",
            variable=self.timeout_mode_var,
            value="fixed",
            command=self._on_execution_option_changed,
        ).grid(row=1, column=2, sticky="w", pady=(6, 0))
        fixed_entry = tk.Entry(options_frame, textvariable=self.timeout_fixed_minutes_var, width=6, relief="solid", borderwidth=1)
        fixed_entry.grid(row=1, column=3, sticky="w", padx=(6, 16), pady=(6, 0))
        fixed_entry.bind("<FocusOut>", lambda _event: self._on_execution_option_changed())

        prediction_frame = ttk.LabelFrame(config_frame, text="Estimation avant lancement", padding=12)
        prediction_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        prediction_frame.columnconfigure(0, weight=1)
        ttk.Label(
            prediction_frame,
            textvariable=self.prediction_var,
            justify="left",
            anchor="w",
            wraplength=820,
        ).grid(row=0, column=0, sticky="ew")

        progress_frame = ttk.LabelFrame(config_frame, text="Execution en cours", padding=12)
        progress_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_frame, maximum=100.0, variable=self.progress_var)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.progress_detail_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        progress_actions = ttk.Frame(progress_frame)
        progress_actions.grid(row=1, column=1, sticky="e", padx=(12, 0))
        self.stop_button = ttk.Button(progress_actions, text="Arrêter", command=self._stop_generation)
        self.stop_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button.state(["disabled"])
        self.open_analysis_button = ttk.Button(progress_actions, text="Ouvrir analyse", command=self._open_analysis)
        self.open_analysis_button.grid(row=0, column=1)
        self.open_analysis_button.state(["disabled"])

        inline_actions = ttk.Frame(config_frame)
        inline_actions.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        inline_actions.columnconfigure(0, weight=1)
        ttk.Label(inline_actions, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.generate_button = ttk.Button(inline_actions, text="Générer le document", command=self._generate)
        self.generate_button.grid(row=0, column=1, sticky="e")
        self.generate_button.state(["disabled"])

        self.participants_frame = ttk.LabelFrame(config_frame, text="Participants")
        self.participants_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.participants_frame.columnconfigure(0, weight=1)
        self.participants_frame.rowconfigure(0, weight=1)

        self.participants_canvas = tk.Canvas(self.participants_frame, height=220, highlightthickness=0)
        self.participants_canvas.grid(row=0, column=0, sticky="nsew")
        participants_scrollbar = ttk.Scrollbar(self.participants_frame, orient="vertical", command=self.participants_canvas.yview)
        participants_scrollbar.grid(row=0, column=1, sticky="ns")
        self.participants_canvas.configure(yscrollcommand=participants_scrollbar.set)

        self.participants_inner = ttk.Frame(self.participants_canvas)
        self.participants_inner.columnconfigure(1, weight=1)
        self.participants_canvas_window = self.participants_canvas.create_window((0, 0), window=self.participants_inner, anchor="nw")
        self.participants_inner.bind("<Configure>", self._on_participants_configure)
        self.participants_canvas.bind("<Configure>", self._on_participants_canvas_configure)
        self.participants_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        log_frame = ttk.LabelFrame(self.root, text="Journal", padding=16)
        log_frame.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=14)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.insert("1.0", "Le document généré, les estimations et les avertissements apparaîtront ici.\n")
        self.log_text.configure(state="disabled")

    def _open_zip(self) -> None:
        if self._generation_running:
            messagebox.showinfo("Generation en cours", "Attendez la fin ou arrêtez la génération avant d’ouvrir un autre zip.")
            return
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
        self.performance_report_var.set(state.write_performance_report)
        self.timeout_mode_var.set(state.timeout_mode)
        self.timeout_multiplier_var.set(f"{state.timeout_multiplier:.1f}")
        self.timeout_fixed_minutes_var.set(f"{state.timeout_fixed_seconds / 60.0:.0f}")
        self._set_output_path(str(state.output_docx))
        self._render_participants(state)
        self.generate_button.state(["!disabled"])
        self.status_var.set(f"Zip chargé : {zip_path.name}")
        self._append_log(f"Session ouverte pour {zip_path.name}")
        self._analysis_path = None
        self._performance_dashboard_path = None
        self._performance_report_path = None
        self.open_analysis_button.state(["disabled"])
        self._update_prediction_preview()

    def _on_drop(self, event) -> None:
        if self._generation_running:
            messagebox.showinfo("Generation en cours", "Attendez la fin ou arrêtez la génération avant d’ouvrir un autre zip.")
            return
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
        self._update_prediction_preview()

    def _on_profile_changed(self, _event=None) -> None:
        if self.state is None:
            return
        profile_name = self.profile_var.get()
        if not profile_name:
            return
        self.state = self.state.with_profile(profile_name)
        self._append_log(f"Profil sélectionné : {profile_name}")
        self._update_prediction_preview()

    def _on_execution_option_changed(self) -> None:
        if self.state is None:
            return
        self.state = self._collect_state()
        self._update_prediction_preview()

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
            entry.bind("<FocusOut>", lambda _event: self._on_execution_option_changed())
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
        state = state.with_performance_report(bool(self.performance_report_var.get()))
        state = state.with_timeout_mode(self.timeout_mode_var.get())
        state = state.with_timeout_multiplier(self._parse_float(self.timeout_multiplier_var.get(), default=2.0))
        fixed_minutes = self._parse_float(self.timeout_fixed_minutes_var.get(), default=15.0)
        state = state.with_timeout_fixed_seconds(fixed_minutes * 60.0)
        return state

    def _generate(self) -> None:
        if self.state is None or self._generation_running:
            return
        state = self._collect_state()
        prediction = state.workload_prediction()
        timeout_seconds = prediction.timeout_seconds(
            state.timeout_mode,
            state.timeout_multiplier,
            state.timeout_fixed_seconds,
        )
        request = state.build_request()

        self.state = state
        self._current_state = state
        self._current_prediction = prediction
        self._current_timeout_seconds = timeout_seconds
        self._analysis_path = None
        self._performance_dashboard_path = None
        self._performance_report_path = None
        self.open_analysis_button.state(["disabled"])

        unique_urls = prediction.summary.unique_url_count
        video_count = prediction.summary.video_attachment_count
        context_bits: list[str] = [f"prevu {prediction.total_seconds:.0f}s"]
        if unique_urls:
            context_bits.append(f"{unique_urls} liens")
        if video_count:
            context_bits.append(f"{video_count} videos")
        self._generation_context = ", ".join(context_bits)
        self._generation_running = True
        self._generation_started_at = time.monotonic()
        self.generate_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.progress_var.set(0.0)
        self._append_log("Lancement de la génération…")
        self._append_log(f"Estimation totale : {prediction.total_seconds:.1f}s")
        self._append_log(f"Timeout actif : {timeout_seconds:.1f}s")
        for stage in prediction.stage_estimates:
            self._append_log(f"Prevision {stage.label} : {stage.predicted_seconds:.1f}s ({stage.detail})")

        ctx = mp.get_context("spawn")
        result_queue = ctx.Queue()
        process = ctx.Process(
            target=_generation_process_main,
            args=(request, self._default_drive_config(), result_queue),
            daemon=True,
        )
        self._generation_queue = result_queue
        self._generation_process = process
        process.start()

        self._refresh_generation_status()
        self._poll_generation_queue()

    def _poll_generation_queue(self) -> None:
        if not self._generation_running:
            return
        assert self._generation_process is not None
        assert self._current_state is not None
        assert self._current_prediction is not None

        elapsed = time.monotonic() - self._generation_started_at
        if self._current_timeout_seconds and elapsed >= self._current_timeout_seconds:
            self._terminate_generation_process()
            self._finalize_interrupted_run(
                status="timeout",
                message="Generation interrompue car le timeout a ete atteint.",
                elapsed_seconds=elapsed,
            )
            return

        received = False
        if self._generation_queue is not None:
            try:
                payload = self._generation_queue.get_nowait()
            except queue.Empty:
                payload = None
            if payload is not None:
                received = True
                if payload.get("status") == "success":
                    result = payload["result"]
                    self._generation_succeeded(self._current_state, result, self._current_prediction, self._current_timeout_seconds)
                    return
                self._generation_failed(
                    RuntimeError(payload.get("message", "Unknown generation error")),
                    payload.get("details"),
                    prediction=self._current_prediction,
                    timeout_seconds=self._current_timeout_seconds,
                )
                return

        if not received and not self._generation_process.is_alive():
            exit_code = self._generation_process.exitcode
            self._generation_failed(
                RuntimeError(f"Generation process ended unexpectedly (exit code {exit_code})."),
                None,
                prediction=self._current_prediction,
                timeout_seconds=self._current_timeout_seconds,
            )
            return

        self.root.after(300, self._poll_generation_queue)

    def _generation_succeeded(
        self,
        state: AssistantState,
        result: EngineResult,
        prediction: TimingPrediction,
        timeout_seconds: float,
    ) -> None:
        self.state = state
        self._cleanup_generation_state()
        self.progress_var.set(100.0)
        self.status_var.set("Document généré.")
        self.progress_detail_var.set("Generation terminee.")
        self._append_log(f"Document généré : {result.output_docx}")
        for warning in result.warnings:
            self._append_log(f"Avertissement [{warning.code}] : {warning.message}")
        for line in result.logs:
            self._append_log(line)

        if result.performance_report_path is not None:
            comparison = comparison_from_performance_report(
                prediction,
                result.performance_report_path,
                status="completed",
                timeout_seconds=timeout_seconds,
            )
            comparison_path = result.output_docx.with_name(f"{result.output_docx.stem}-prediction-vs-actual.txt")
            write_prediction_comparison(comparison, comparison_path)
            append_timing_history(make_history_entry(prediction, result.performance_report_path))
            self._analysis_path = comparison_path
            self._performance_dashboard_path = result.performance_svg_path
            self._performance_report_path = result.performance_report_path
            self.open_analysis_button.state(["!disabled"])
            self._append_log(f"Analyse prediction vs reel : {comparison_path}")
            if result.performance_svg_path is not None:
                self._append_log(f"Dashboard performance : {result.performance_svg_path}")
        else:
            self._append_log("Rapport de performance non demande pour ce run.")

        messagebox.showinfo("Génération terminée", f"Document généré :\n{result.output_docx}")

    def _generation_failed(
        self,
        exc: Exception,
        details: str | None = None,
        *,
        prediction: TimingPrediction | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        elapsed = max(0.0, time.monotonic() - self._generation_started_at) if self._generation_started_at else 0.0
        self._cleanup_generation_state()
        self.status_var.set("Échec de génération.")
        self.progress_detail_var.set("Generation echouee.")
        self._append_log(f"Erreur : {exc}")
        if details:
            self._append_log(details.rstrip())
        if prediction is not None:
            comparison = comparison_for_interrupted_run(
                prediction,
                status="failed",
                elapsed_seconds=elapsed,
                timeout_seconds=timeout_seconds,
            )
            if self.state is not None:
                comparison_path = self.state.output_docx.with_name(f"{self.state.output_docx.stem}-prediction-vs-actual.txt")
                write_prediction_comparison(comparison, comparison_path)
                self._analysis_path = comparison_path
                self.open_analysis_button.state(["!disabled"])
                self._append_log(f"Analyse prediction vs reel : {comparison_path}")
        messagebox.showerror("Génération impossible", str(exc))

    def _stop_generation(self) -> None:
        if not self._generation_running:
            return
        elapsed = time.monotonic() - self._generation_started_at
        self._terminate_generation_process()
        self._finalize_interrupted_run(
            status="stopped",
            message="Generation arretee manuellement.",
            elapsed_seconds=elapsed,
        )

    def _finalize_interrupted_run(self, status: str, message: str, elapsed_seconds: float) -> None:
        prediction = self._current_prediction
        timeout_seconds = self._current_timeout_seconds
        self._cleanup_generation_state()
        self.status_var.set("Generation interrompue.")
        self.progress_detail_var.set(message)
        self._append_log(message)
        if prediction is not None and self.state is not None:
            comparison = comparison_for_interrupted_run(
                prediction,
                status=status,
                elapsed_seconds=elapsed_seconds,
                timeout_seconds=timeout_seconds,
            )
            comparison_path = self.state.output_docx.with_name(f"{self.state.output_docx.stem}-prediction-vs-actual.txt")
            write_prediction_comparison(comparison, comparison_path)
            self._analysis_path = comparison_path
            self.open_analysis_button.state(["!disabled"])
            self._append_log(f"Analyse prediction vs reel : {comparison_path}")
        messagebox.showinfo("Generation interrompue", message)

    def _cleanup_generation_state(self) -> None:
        self._generation_running = False
        self.generate_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        self._terminate_generation_process()

    def _terminate_generation_process(self) -> None:
        process = self._generation_process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        self._generation_process = None
        self._generation_queue = None

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

    def _update_prediction_preview(self) -> None:
        if self.state is None:
            self.prediction_var.set("Chargez un ZIP pour obtenir une estimation.")
            return
        try:
            state = self._collect_state()
            prediction = state.workload_prediction()
            timeout_seconds = prediction.timeout_seconds(
                state.timeout_mode,
                state.timeout_multiplier,
                state.timeout_fixed_seconds,
            )
        except Exception as exc:
            self.prediction_var.set(f"Estimation indisponible: {exc}")
            return

        lines = [
            f"Volume: {prediction.summary.message_count} messages, {prediction.summary.unique_url_count} URLs uniques, "
            f"{prediction.summary.audio_attachment_count} audio(s), {prediction.summary.video_attachment_count} video(s).",
            f"Duree totale estimee: {prediction.total_seconds:.1f}s. Timeout actif: {timeout_seconds:.1f}s.",
        ]
        for stage in prediction.stage_estimates:
            lines.append(f"{stage.label}: {stage.predicted_seconds:.1f}s")
        lines.append(
            "Rapport de performance: "
            + ("oui (JSON/TXT/SVG + comparaison prediction/reel)" if state.write_performance_report else "non")
        )
        self.prediction_var.set("\n".join(lines))

    def _open_analysis(self) -> None:
        target = self._analysis_path or self._performance_dashboard_path or self._performance_report_path
        if target is None:
            return
        try:
            subprocess.run(["open", str(target)], check=False)
        except OSError as exc:
            messagebox.showerror("Ouverture impossible", str(exc))

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
        elapsed = time.monotonic() - self._generation_started_at
        predicted = self._current_prediction.total_seconds if self._current_prediction is not None else 0.0
        timeout_seconds = self._current_timeout_seconds
        if predicted > 0:
            progress = min(99.0, (elapsed / predicted) * 100.0)
            self.progress_var.set(progress)
            self.progress_detail_var.set(
                f"{elapsed:.0f}s écoulées / {predicted:.0f}s prévues"
                + (f" · timeout {timeout_seconds:.0f}s" if timeout_seconds else "")
            )
        else:
            self.progress_var.set(0.0)
            self.progress_detail_var.set(f"{elapsed:.0f}s écoulées")

        if self._generation_context:
            self.status_var.set(f"Génération en cours… {self._generation_context} ({elapsed:.0f}s)")
        else:
            self.status_var.set(f"Génération en cours… ({elapsed:.0f}s)")
        self.root.after(1000, self._refresh_generation_status)

    def _parse_float(self, raw: str, default: float) -> float:
        try:
            return float(raw.replace(",", ".").strip())
        except (AttributeError, ValueError):
            return default

    def _default_drive_config(self) -> DriveConfig:
        return DriveConfig(
            credentials_path=Path("secrets/client_secret_819489726933-ku0rotlcdumi2nphpfoqquun51krl2ah.apps.googleusercontent.com.json"),
            token_path=Path("secrets/google_drive_token.json"),
        )


def run_desktop_app() -> None:
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    run_desktop_app()
