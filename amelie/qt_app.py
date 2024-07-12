#!/usr/bin/env python

import sys
import time
import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
QComboBox,
QHBoxLayout
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import whisper
import tqdm




from typing import Union

class ProgressListener:
    def on_progress(self, current: Union[int, float], total: Union[int, float]):
        self.total = total

    def on_finished(self):
        pass


import sys
import threading
from typing import List, Union
import tqdm


class ProgressListenerHandle:
    def __init__(self, listener: ProgressListener):
        self.listener = listener

    def __enter__(self):
        register_thread_local_progress_listener(self.listener)

    def __exit__(self, exc_type, exc_val, exc_tb):
        unregister_thread_local_progress_listener(self.listener)

        if exc_type is None:
            self.listener.on_finished()


class _CustomProgressBar(tqdm.tqdm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current = self.n  # Set the initial value

    def update(self, n):
        #super().update(n)
        # Because the progress bar might be disabled, we need to manually update the progress
        self._current += n

        # Inform listeners
        listeners = _get_thread_local_listeners()

        for listener in listeners:
            listener.on_progress(self._current, self.total)


_thread_local = threading.local()


def _get_thread_local_listeners():
    if not hasattr(_thread_local, 'listeners'):
        _thread_local.listeners = []
    return _thread_local.listeners


_hooked = False


def init_progress_hook():
    global _hooked

    if _hooked:
        return

    # Inject into tqdm.tqdm of Whisper, so we can see progress
    import whisper.transcribe
    transcribe_module = sys.modules['whisper.transcribe']
    transcribe_module.tqdm.tqdm = _CustomProgressBar
    _hooked = True


def register_thread_local_progress_listener(progress_listener: ProgressListener):
    # This is a workaround for the fact that the progress bar is not exposed in the API
    init_progress_hook()

    listeners = _get_thread_local_listeners()
    listeners.append(progress_listener)


def unregister_thread_local_progress_listener(progress_listener: ProgressListener):
    listeners = _get_thread_local_listeners()

    if progress_listener in listeners:
        listeners.remove(progress_listener)


def create_progress_listener_handle(progress_listener: ProgressListener):
    return ProgressListenerHandle(progress_listener)


@dataclasses.dataclass
class Result:
    text: str
    duration: float




def process(lines: List[str]):
    print(lines)
    # remove all double lines, that could not be removed before
    final_lines = []
    last_one = ''
    sentences = lines.split('. ')
    for sentence in sentences:
        #print(sentence, end='')
        if last_one and final_lines[-1] == sentence:
            last_one = sentence
            #print(f' ...  removed')
            continue
        #print(f' ...  added')
        final_lines.append(f'{sentence}')
        last_one = sentence
    final_lines = '. '.join(final_lines)
    print(final_lines)
    return final_lines



class TranscriptionThread(QThread):
    """Thread class for transcribing audio file."""

    progress_signal = pyqtSignal(int)
    finished_transcription = pyqtSignal(Result)

    def __init__(self, audio_file: Path, model: str, language: str):
        super().__init__()

        self.audio_file = audio_file
        self.model = model
        self.language = language
        self.stopped = False

    def run(self):
        print(f'start whisper with model size {self.model} and language {self.language}')
        ts = time.time()
        try:

            class PrintingProgressListener:

                def __init__(self, progress_signal):
                    self.progress_signal = progress_signal

                def on_progress(self, current: Union[int, float], total: Union[int, float]):
                    #print(f"Progress: {current}/{total}")
                    self.progress_signal.emit(int(current/total*100))

                def on_finished(self):
                    print("Finished")

            import whisper

            model = whisper.load_model(self.model)

            with create_progress_listener_handle(PrintingProgressListener(self.progress_signal)) as listener:
                # Set verbose to None to disable the progress bar, as we are using our own
                result = model.transcribe(str(self.audio_file), language=self.language, fp16=False, verbose=False)

            if not self.stopped:
                self.finished_transcription.emit(Result(text=result["text"], duration=time.time()-ts))
        except Exception as e:
            if not self.stopped:
                self.finished_transcription.emit(
                    Result(
                        text=f"Error occurred during transcription: {str(e)}",
                        duration=time.time()-ts)
                )

    def stop(self):
        self.stopped = True

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fast Rabbit Session To Text")

        self.audio_file_path: Optional[Path] = None
        self.model_options = ["tiny", "base", "small", "medium", "large"]
        self.selected_model = "tiny"
        self.languages = ["de","en"]
        self.language = "de"
        self.transcription_result = ""

        self.init_ui()

    def init_ui(self):
        self.file_label = QLabel("No file selected", self)

        self.select_file_button = QPushButton("Select Audio File", self)
        self.select_file_button.clicked.connect(self.select_file)

        self.transcribe_button = QPushButton("Transcribe", self)
        self.transcribe_button.clicked.connect(self.start_transcription)

        self.model_combo_box = QComboBox(self)
        self.model_combo_box.addItems(self.model_options)
        self.model_combo_box.setCurrentText(self.selected_model)
        self.model_combo_box.activated[str].connect(self.select_model)

        self.lang_combo_box = QComboBox(self)
        self.lang_combo_box.addItems(self.languages)
        self.lang_combo_box.setCurrentText(self.language)
        self.lang_combo_box.activated[str].connect(self.select_lang)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)

        self.image_label = QLabel(self)
        pixmap = QPixmap("rabbit.png")
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(640, 640)
        self.image_label.setScaledContents(True)

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(self.file_label)
        layout.addWidget(self.select_file_button)

        hbox_layout = QHBoxLayout()
        hbox_layout.addWidget(self.lang_combo_box)
        hbox_layout.addWidget(self.model_combo_box)
        hbox_layout.addWidget(self.transcribe_button)
        layout.addLayout(hbox_layout)

        layout.addWidget(self.progress_bar)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.show()

    def select_file(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Audio files (*.wav *.mp4 *.m4a *.mp3)")
        file_dialog.setViewMode(QFileDialog.Detail)
        if file_dialog.exec_():
            self.audio_file_path = Path(file_dialog.selectedFiles()[0])
            self.file_label.setText(str(self.audio_file_path))

    def select_model(self, text):
        self.selected_model = text

    def select_lang(self, text):
        self.language = text

    def start_transcription(self):
        if not self.audio_file_path:
            QMessageBox.warning(
                self, "Warning", "Please select an audio file first."
            )
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.transcribe_button.setEnabled(False)
        self.select_file_button.setEnabled(False)
        self.model_combo_box.setEnabled(False)

        self.transcribe_thread = TranscriptionThread(
            self.audio_file_path, model=self.selected_model, language=self.language
        )
        self.transcribe_thread.progress_signal.connect(self.update_progress)
        self.transcribe_thread.finished_transcription.connect(
            self.handle_transcription_finished
        )
        self.transcribe_thread.start()

    def update_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def handle_transcription_finished(self, result: Result):
        self.transcription_result = result.text
        self.progress_bar.setVisible(False)
        if not self.transcription_result.startswith("Error"):

            file_name = self.audio_file_path.with_suffix(".txt").name

            done_dir = self.audio_file_path.parent / 'done'
            done_dir.mkdir(exist_ok=True)

            with open(done_dir / file_name, "w") as f:
                f.write(self.transcription_result)

            output_dir = self.audio_file_path.parent / 'processed_output'
            output_dir.mkdir(exist_ok=True)

            processed = process(self.transcription_result)

            with open(output_dir / file_name , "w") as f:
                f.write(processed)


            duration_m = result.duration // 60
            duration_s = result.duration % 60

            QMessageBox.information(
                self,
                "Transcription Completed ",
                f"Transcription saved at {done_dir / file_name}, "
                f"Processed saved at {output_dir / file_name}, "
                f"took: {duration_m:.2f} min {duration_s:.2f} s",
            )
        else:
            QMessageBox.critical(self, "Error", result)
        self.transcribe_button.setEnabled(True)
        self.select_file_button.setEnabled(True)
        self.model_combo_box.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
