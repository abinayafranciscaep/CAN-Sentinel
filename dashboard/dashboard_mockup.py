"""
dashboard_mockup.py - styled, resizable CAN-Sentinel dashboard.

Data sources (all optional; the dashboard falls back to sample data):
    dashboard/sample_alert.json   -> alert card, threat gauge, alert count
    data/normal_run*_*.csv        -> traffic table and frames/second
                                     (newest file by modification time)

Nothing is read from the live CAN bus. When files load, the banner says
"REPLAYING RECORDED FILE" so the dashboard never implies live detection.

Run from the repository root:
    py dashboard/dashboard_mockup.py

Car image:
    dashboard/assets/can_sentinel_car.png
"""

import csv
import html
import json
import sys
from collections import deque
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap, QKeySequence, QShortcut, QTransform
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHeaderView,
    QLabel,
    QMainWindow,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QSlider,
    QSizePolicy,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).resolve().parent
DATA_DIR = DASHBOARD_DIR.parent / "data"
ALERT_FILE = DASHBOARD_DIR / "sample_alert.json"

IMAGE_CANDIDATES = [
    DASHBOARD_DIR / "assets" / "can_sentinel_car.png",
    DASHBOARD_DIR / "assests" / "can_sentinel_car.png",
    DASHBOARD_DIR / "can_sentinel_car.png",
]

CAR_IMAGE_PATH = next(
    (path for path in IMAGE_CANDIDATES if path.is_file()),
    IMAGE_CANDIDATES[0],
)

# ---------------------------------------------------------------------------
# Fallback sample data (used only when the real files are missing/malformed)
# ---------------------------------------------------------------------------

SAMPLE_THREAT = 25
SAMPLE_FPS = "320"
SAMPLE_ROWS = [
    ("1791300000.123456", "0x0A0", "8", "3201000000000017", "OK"),
    ("1791300000.133502", "0x0B0", "8", "00FA000000000042", "OK"),
    ("1791300000.143611", "0x100", "8", "0BB5000000000009", "OK"),
    ("1791300042.501223", "0x0A0", "8", "6400000000000099", "ALERT"),
    ("1791300042.511400", "0x200", "8", "3C00000000000012", "OK"),
]

REQUIRED_ALERT_FIELDS = {
    "timestamp", "attack_type", "suspect_id", "confidence",
    "severity", "affected_system", "detection_layer", "technique",
}
REQUIRED_CSV_FIELDS = {"timestamp", "can_id", "dlc", "data_hex", "label"}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_alert(path):
    """Return the alert dict, or None if missing, malformed or incomplete."""
    try:
        with open(path, encoding="utf-8") as f:
            alert = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(alert, dict) or not REQUIRED_ALERT_FIELDS <= alert.keys():
        return None

    try:
        alert["confidence"] = float(alert["confidence"])
    except (TypeError, ValueError):
        return None

    return alert


def find_recording(data_dir):
    """Newest data/normal_run*_*.csv, or None."""
    try:
        files = sorted(
            data_dir.glob("normal_run*_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return files[0] if files else None


def load_recording(path, n=5):
    """
    One pass over a recorded CSV.
    Returns (last_n_rows, frames_per_second, filename) or None on any problem.
    Rows are (timestamp, can_id, dlc, data_hex, status).
    """
    if path is None:
        return None

    tail = deque(maxlen=n)
    count = 0
    first_ts = last_ts = None

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not REQUIRED_CSV_FIELDS <= set(reader.fieldnames):
                return None
            for r in reader:
                ts = float(r["timestamp"])
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
                count += 1
                status = "OK" if r["label"] == "normal" else "ALERT"
                tail.append((r["timestamp"], r["can_id"], r["dlc"], r["data_hex"], status))
    except (OSError, ValueError, KeyError):
        return None

    if count < 2 or last_ts is None or last_ts <= first_ts:
        return None

    fps = count / (last_ts - first_ts)
    return list(tail), fps, Path(path).name


# Load everything once at start-up.
ALERT = load_alert(ALERT_FILE)
RECORDING = load_recording(find_recording(DATA_DIR))

if RECORDING:
    ROWS, _fps, RECORDING_NAME = RECORDING
    FRAMES_PER_SECOND = f"{_fps:.0f}"
else:
    ROWS, FRAMES_PER_SECOND, RECORDING_NAME = SAMPLE_ROWS, SAMPLE_FPS, None

if ALERT:
    # Placeholder mapping: confidence -> 0-100. Agree the real one with the ML lead.
    THREAT = max(0, min(100, int(round(ALERT["confidence"] * 100))))
    ALERT_COUNT = "1"
else:
    THREAT = 0 if RECORDING else SAMPLE_THREAT
    ALERT_COUNT = "0" if RECORDING else "1"

USING_FILES = bool(ALERT) or bool(RECORDING)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

STYLE = """
QMainWindow {
    background-color: #07111F;
}

QWidget#root, QWidget#content {
    background-color: #07111F;
}

QLabel {
    color: #DCE8F7;
    background-color: transparent;
}

QLabel#heading {
    font-size: 32px;
    font-weight: bold;
    color: #FFFFFF;
}

QLabel#headingAccent {
    font-size: 32px;
    font-weight: bold;
    color: #20B8FF;
}

QLabel#sub {
    color: #9FB4CE;
    font-size: 13px;
}

QLabel#muted {
    color: #94A3B8;
    font-size: 11px;
}

QLabel#cardTitle {
    color: #A9BED7;
    font-size: 12px;
}

QLabel#cardValue {
    font-size: 30px;
    font-weight: bold;
}

QFrame#card {
    background-color: #101F33;
    border: 1px solid #203B59;
    border-radius: 12px;
}

QFrame#alertCard {
    background-color: #211521;
    border: 1px solid #8D2736;
    border-radius: 12px;
}

QFrame#alertCardEmpty {
    background-color: #0F2219;
    border: 1px solid #1F6B45;
    border-radius: 12px;
}

QFrame#trafficCard {
    background-color: #0D1A2B;
    border: 1px solid #203B59;
    border-radius: 12px;
}

QProgressBar {
    background-color: #20344C;
    border: none;
    border-radius: 6px;
    max-height: 13px;
    min-height: 13px;
}

QProgressBar::chunk {
    border-radius: 6px;
}

QTableWidget {
    background-color: #0B1727;
    alternate-background-color: #122238;
    color: #DCE8F7;
    border: 1px solid #203B59;
    border-radius: 7px;
    gridline-color: #20344C;
    selection-background-color: #1B4265;
    selection-color: white;
    font-size: 12px;
}

QHeaderView::section {
    background-color: #1A304A;
    color: #E7F0FC;
    padding: 8px 6px;
    border: none;
    border-right: 1px solid #284563;
    font-weight: bold;
}

QPushButton {
    background-color: #172D46;
    color: #DCE8F7;
    border: 1px solid #294967;
    border-radius: 6px;
    padding: 5px 10px;
}

QPushButton:hover {
    background-color: #214263;
}

QSlider::groove:horizontal {
    background: #20344C;
    height: 5px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #20B8FF;
    width: 13px;
    margin: -5px 0;
    border-radius: 6px;
}

QScrollArea {
    background-color: #07111F;
    border: none;
}
"""


def threat_level(score):
    """Map a 0-100 score to a label and a colour."""

    if score < 40:
        return "LOW", "#35E58B"

    if score < 70:
        return "MEDIUM", "#FFB547"

    return "HIGH", "#FF4D5E"


def severity_color(severity):
    """Colour for the severity word in the alert banner."""
    return {
        "low": "#35E58B",
        "medium": "#FFB547",
        "high": "#FF8A4D",
        "critical": "#FF5A66",
    }.get(str(severity).lower(), "#FF5A66")


def make_card(title, value, color, size=30):
    """Create a rounded metric card with a title and a large value."""

    card = QFrame()
    card.setObjectName("card")
    card.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )

    box = QHBoxLayout(card)
    box.setContentsMargins(14, 12, 14, 12)
    box.setSpacing(12)

    # Decorative symbols only; these are not live system indicators.
    symbols = {
        "Frames / second": "∿",
        "Alerts loaded": "!",
        "Threat level": "✓",
    }

    symbol = QLabel(symbols.get(title, "•"))
    symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
    symbol.setFixedSize(48, 48)
    symbol.setStyleSheet(
        f"background-color: #172D46;"
        f"color: {color};"
        "border-radius: 10px;"
        "font-size: 24px;"
        "font-weight: bold;"
    )

    text_box = QVBoxLayout()
    text_box.setSpacing(3)

    title_label = QLabel(title)
    title_label.setObjectName("cardTitle")

    value_label = QLabel(value)
    value_label.setObjectName("cardValue")
    value_label.setStyleSheet(
        f"color: {color}; font-size: {size}px; font-weight: bold;"
    )

    text_box.addWidget(title_label)
    text_box.addWidget(value_label)

    box.addWidget(symbol)
    box.addLayout(text_box, 1)

    return card


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CAN-Sentinel Dashboard (mock-up)")
        self.resize(1440, 900)
        self.setMinimumSize(760, 560)

        self.car_pixmap = QPixmap(str(CAR_IMAGE_PATH))

        # Mirror horizontally so the car faces right to left.
        if not self.car_pixmap.isNull():
            self.car_pixmap = self.car_pixmap.transformed(
                QTransform().scale(-1, 1)
            )

        root = QWidget()
        root.setObjectName("root")

        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        content = QWidget()
        content.setObjectName("content")

        page = QVBoxLayout(content)
        page.setContentsMargins(24, 18, 24, 18)
        page.setSpacing(12)

        # ---------------- Header: title and car image ----------------

        header = QHBoxLayout()
        header.setSpacing(8)

        title_column = QVBoxLayout()
        title_column.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setSpacing(0)

        heading = QLabel("CAN-")
        heading.setObjectName("heading")

        heading_accent = QLabel("Sentinel")
        heading_accent.setObjectName("headingAccent")

        title_row.addWidget(heading)
        title_row.addWidget(heading_accent)
        title_row.addStretch(1)

        subtitle = QLabel("Automotive ECU intrusion detection")
        subtitle.setObjectName("sub")

        # Honest mode banner: says exactly where the numbers came from.
        if USING_FILES:
            parts = []
            parts.append(
                f"traffic: {RECORDING_NAME}" if RECORDING_NAME
                else "traffic: sample rows"
            )
            parts.append(
                f"alert: {ALERT_FILE.name}" if ALERT
                else "alert: none loaded"
            )
            mode_text = "REPLAYING RECORDED FILE  •  NOT LIVE  |  " + "  |  ".join(parts)
        else:
            mode_text = "DEMO MODE  •  STATIC SAMPLE DATA"

        demo_label = QLabel(mode_text)
        demo_label.setObjectName("muted")
        demo_label.setWordWrap(True)

        title_column.addStretch(1)
        title_column.addLayout(title_row)
        title_column.addWidget(subtitle)
        title_column.addWidget(demo_label)
        title_column.addStretch(1)

        self.car_label = QLabel()
        self.car_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.car_label.setMinimumSize(300, 170)
        self.car_label.setMaximumHeight(250)
        self.car_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.car_label.setStyleSheet(
            "background-color: transparent; border: none;"
        )

        if self.car_pixmap.isNull():
            self.car_label.setText(
                "CAR IMAGE NOT FOUND\n\n"
                "Save your image as:\n"
                "dashboard/assets/can_sentinel_car.png"
            )
            self.car_label.setStyleSheet(
                "color: #9FB4CE; background: transparent; border: none;"
            )
        else:
            self.update_car_image()

        header.addLayout(title_column, 2)
        header.addWidget(self.car_label, 3)
        page.addLayout(header)

        # ---------------- Three summary cards ----------------

        name, color = threat_level(THREAT)

        cards = QHBoxLayout()
        cards.setSpacing(12)

        cards.addWidget(
            make_card("Frames / second", FRAMES_PER_SECOND, "#39C5FF")
        )
        cards.addWidget(
            make_card("Alerts loaded", ALERT_COUNT, "#FFB547")
        )
        cards.addWidget(
            make_card("Threat level", name, color)
        )

        page.addLayout(cards)

        # ---------------- Threat score gauge ----------------

        threat_row = QHBoxLayout()
        threat_row.setSpacing(12)

        score_title = QLabel("THREAT SCORE")
        score_title.setStyleSheet(
            "color: #A9BED7; font-size: 12px; font-weight: bold;"
        )

        zero_label = QLabel("0")
        zero_label.setStyleSheet("color: #8EA6C2;")

        gauge = QProgressBar()
        gauge.setRange(0, 100)
        gauge.setValue(THREAT)
        gauge.setTextVisible(False)
        gauge.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {color}; }}"
        )

        score_value = QLabel(f"{THREAT} / 100")
        score_value.setStyleSheet(
            "color: #C8D8EB; font-size: 13px; font-weight: bold;"
        )

        threat_row.addWidget(score_title)
        threat_row.addWidget(zero_label)
        threat_row.addWidget(gauge, 1)
        threat_row.addWidget(score_value)

        page.addLayout(threat_row)

        # ---------------- Latest alert banner ----------------

        alert_card = QFrame()
        alert_layout = QHBoxLayout(alert_card)
        alert_layout.setContentsMargins(16, 10, 16, 10)
        alert_layout.setSpacing(12)

        alert_icon = QLabel()
        alert_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        alert_icon.setFixedSize(46, 46)

        alert_text = QVBoxLayout()

        alert_title = QLabel("Latest alert")
        alert_title.setStyleSheet("color: #B7C8DB; font-size: 12px;")

        alert_detail = QLabel()
        alert_detail.setTextFormat(Qt.TextFormat.RichText)
        alert_detail.setWordWrap(True)
        alert_detail.setStyleSheet("font-size: 15px;")

        if ALERT:
            alert_card.setObjectName("alertCard")
            alert_icon.setText("!")
            alert_icon.setStyleSheet(
                "background-color: #3B1C2A;"
                "color: #FF5A66;"
                "border-radius: 10px;"
                "font-size: 28px;"
                "font-weight: bold;"
            )

            sev = str(ALERT["severity"])
            sev_col = severity_color(sev)
            e = html.escape  # file content is untrusted; escape before rich text

            alert_detail.setText(
                f'<span style="color:#FF5A66;font-weight:bold;">'
                f'{e(str(ALERT["attack_type"]))} on {e(str(ALERT["suspect_id"]))}</span>'
                f'<span style="color:#DCE8F7;">'
                f'  |  confidence {ALERT["confidence"]:.2f}'
                f'  |  {e(str(ALERT["affected_system"]))}'
                f'  |  layer {e(str(ALERT["detection_layer"]))}'
                f'  |  {e(str(ALERT["technique"]))}'
                f'  |  severity </span>'
                f'<span style="color:{sev_col};font-weight:bold;">{e(sev)}</span>'
            )
        else:
            alert_card.setObjectName("alertCardEmpty")
            alert_icon.setText("✓")
            alert_icon.setStyleSheet(
                "background-color: #12372A;"
                "color: #35E58B;"
                "border-radius: 10px;"
                "font-size: 28px;"
                "font-weight: bold;"
            )
            alert_detail.setText(
                '<span style="color:#35E58B;font-weight:bold;">No alerts</span>'
            )

        alert_text.addWidget(alert_title)
        alert_text.addWidget(alert_detail)

        alert_layout.addWidget(alert_icon)
        alert_layout.addLayout(alert_text, 1)

        page.addWidget(alert_card)

        # ---------------- Recent CAN traffic table ----------------

        traffic_card = QFrame()
        traffic_card.setObjectName("trafficCard")

        traffic_layout = QVBoxLayout(traffic_card)
        traffic_layout.setContentsMargins(12, 9, 12, 10)
        traffic_layout.setSpacing(8)

        traffic_heading = QHBoxLayout()

        traffic_icon = QLabel("▤")
        traffic_icon.setStyleSheet(
            "color: #7EC8FF; font-size: 20px;"
        )

        traffic_title = QLabel("RECENT CAN TRAFFIC")
        traffic_title.setStyleSheet(
            "color: #E8F2FF; font-size: 14px; font-weight: bold;"
        )

        badge_text = (
            f"LAST {len(ROWS)} ROWS OF {RECORDING_NAME}"
            if RECORDING_NAME else "SAMPLE DATA"
        )
        sample_badge = QLabel(badge_text)
        sample_badge.setStyleSheet(
            "color: #8FA9C5;"
            "background-color: #172D46;"
            "padding: 5px 8px;"
            "border-radius: 6px;"
            "font-size: 10px;"
            "font-weight: bold;"
        )

        traffic_heading.addWidget(traffic_icon)
        traffic_heading.addWidget(traffic_title)
        traffic_heading.addStretch(1)
        traffic_heading.addWidget(sample_badge)

        traffic_layout.addLayout(traffic_heading)

        table = QTableWidget(len(ROWS), 5)
        table.setHorizontalHeaderLabels(
            ["timestamp", "can_id", "dlc", "data_hex", "status"]
        )

        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)

        table.setAlternatingRowColors(True)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for r, row in enumerate(ROWS):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))

                if c == 4:
                    if value == "ALERT":
                        item.setForeground(QColor("#FF5A66"))
                        item.setText("●  ALERT")
                    else:
                        item.setForeground(QColor("#35E58B"))
                        item.setText("●  OK")

                table.setItem(r, c, item)

        table.setMinimumHeight(155)
        table.setMaximumHeight(195)

        traffic_layout.addWidget(table)
        page.addWidget(traffic_card)

        footer = QLabel(
            "CAN-SENTINEL  •  AUTOMOTIVE SECURITY MONITORING CONCEPT"
            "  |  NOT CONNECTED TO LIVE CAN"
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #6F89A7; font-size: 10px;")

        page.addWidget(footer)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        # ---------------- Zoom controls ----------------

        zoom_bar = QHBoxLayout()
        zoom_bar.setContentsMargins(12, 5, 12, 5)
        zoom_bar.setSpacing(8)

        zoom_title = QLabel("ZOOM")
        zoom_title.setStyleSheet(
            "color: #9FB4CE; font-size: 10px; font-weight: bold;"
        )

        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(34)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(80, 120)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(130)

        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(34)

        self.zoom_value = QLabel("100%")
        self.zoom_value.setMinimumWidth(42)

        reset_button = QPushButton("Reset")

        zoom_out.clicked.connect(
            lambda: self.zoom_slider.setValue(
                max(80, self.zoom_slider.value() - 5)
            )
        )
        zoom_in.clicked.connect(
            lambda: self.zoom_slider.setValue(
                min(120, self.zoom_slider.value() + 5)
            )
        )
        reset_button.clicked.connect(
            lambda: self.zoom_slider.setValue(100)
        )
        self.zoom_slider.valueChanged.connect(self.set_zoom)

        zoom_bar.addStretch(1)
        zoom_bar.addWidget(zoom_title)
        zoom_bar.addWidget(zoom_out)
        zoom_bar.addWidget(self.zoom_slider)
        zoom_bar.addWidget(zoom_in)
        zoom_bar.addWidget(self.zoom_value)
        zoom_bar.addWidget(reset_button)
        zoom_bar.addStretch(1)

        zoom_container = QWidget()
        zoom_container.setLayout(zoom_bar)
        zoom_container.setStyleSheet(
            "background-color: #0B1727;"
            "border-top: 1px solid #203B59;"
        )

        outer_layout.addWidget(zoom_container)

        QShortcut(
            QKeySequence("Ctrl++"),
            self,
            activated=lambda: self.zoom_slider.setValue(
                min(120, self.zoom_slider.value() + 5)
            ),
        )
        QShortcut(
            QKeySequence("Ctrl+-"),
            self,
            activated=lambda: self.zoom_slider.setValue(
                max(80, self.zoom_slider.value() - 5)
            ),
        )
        QShortcut(
            QKeySequence("Ctrl+0"),
            self,
            activated=lambda: self.zoom_slider.setValue(100),
        )

        self.setCentralWidget(root)

    def update_car_image(self):
        """Resize the car image to fit the header without stretching it."""

        if self.car_pixmap.isNull():
            return

        target_size = self.car_label.size()

        if target_size.width() < 2 or target_size.height() < 2:
            return

        self.car_label.setPixmap(
            self.car_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        """Refresh the car image whenever the window is resized."""
        super().resizeEvent(event)

        if hasattr(self, "car_label"):
            self.update_car_image()

    def set_zoom(self, value):
        """Adjust the interface font size while preserving the dark theme."""

        self.zoom_value.setText(f"{value}%")

        font = self.font()
        font.setPointSizeF(9 * value / 100)
        self.centralWidget().setFont(font)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    window = Dashboard()
    window.show()

    sys.exit(app.exec())