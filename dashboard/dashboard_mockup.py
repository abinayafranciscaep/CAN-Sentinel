"""dashboard_mockup.py - styled layout mock-up of the CAN-Sentinel dashboard.
Static sample data only; nothing is read from the bus yet.
Run from the repo root:  py dashboard/dashboard_mockup.py"""
import sys

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QHeaderView, QLabel,
                             QMainWindow, QProgressBar, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget, QHBoxLayout)

THREAT = 25   # sample threat score 0-100; later this comes from the alert JSON

# Qt style sheet: CSS-like rules. "#name" selects a widget by its objectName.
STYLE = """
QMainWindow, QWidget#root { background: #0F172A; }
QLabel { color: #E2E8F0; }
QLabel#heading { font-size: 24px; font-weight: bold; color: white; }
QLabel#sub { color: #94A3B8; font-size: 12px; }
QFrame#card { background: #1E293B; border-radius: 10px; }
QLabel#cardTitle { color: #94A3B8; font-size: 12px; }
QProgressBar { background: #334155; border: none; border-radius: 6px; max-height: 12px; }
QProgressBar::chunk { border-radius: 6px; }
QTableWidget { background: #1E293B; color: #E2E8F0; border: none;
               gridline-color: #334155; alternate-background-color: #243247; }
QHeaderView::section { background: #334155; color: #E2E8F0; padding: 6px;
                       border: none; font-weight: bold; }
"""

# Sample rows in the CSV schema plus a status column (OK or ALERT).
ROWS = [("1791300000.123456", "0x0A0", "8", "3201000000000017", "OK"),
        ("1791300000.133502", "0x0B0", "8", "00FA000000000042", "OK"),
        ("1791300000.143611", "0x100", "8", "0BB5000000000009", "OK"),
        ("1791300042.501223", "0x0A0", "8", "6400000000000099", "ALERT"),
        ("1791300042.511400", "0x200", "8", "3C00000000000012", "OK")]


def threat_level(score):
    """Map a 0-100 score to a label and a colour."""
    if score < 40:
        return "LOW", "#22C55E"
    if score < 70:
        return "MEDIUM", "#F59E0B"
    return "HIGH", "#EF4444"


def make_card(title, value, color, size=26):
    """A rounded 'card' with a small title and a big coloured value."""
    card = QFrame()
    card.setObjectName("card")
    box = QVBoxLayout(card)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    v = QLabel(value)
    v.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: bold;")
    box.addWidget(t)
    box.addWidget(v)
    return card


class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN-Sentinel Dashboard (mock-up)")
        self.resize(900, 600)
        root = QWidget()
        root.setObjectName("root")
        page = QVBoxLayout(root)              # stacks sections top to bottom
        page.setContentsMargins(22, 18, 22, 18)
        page.setSpacing(14)

        heading = QLabel("CAN-Sentinel")
        heading.setObjectName("heading")
        sub = QLabel("Automotive ECU intrusion detection | mock-up with sample data")
        sub.setObjectName("sub")
        page.addWidget(heading)
        page.addWidget(sub)

        # Row of three summary cards.
        name, color = threat_level(THREAT)
        cards = QHBoxLayout()                 # side by side
        cards.setSpacing(14)
        cards.addWidget(make_card("Frames / second", "320", "#38BDF8"))
        cards.addWidget(make_card("Alerts (last 10 min)", "1", "#F59E0B"))
        cards.addWidget(make_card("Threat level", name, color))
        page.addLayout(cards)

        # Threat gauge: a progress bar coloured by threat level.
        gauge = QProgressBar()
        gauge.setRange(0, 100)
        gauge.setValue(THREAT)
        gauge.setTextVisible(False)
        gauge.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
        page.addWidget(gauge)

        # Latest alert, using the fields of the alert JSON (design doc, Section 5.3).
        page.addWidget(make_card("Latest alert",
                                 "spoof_brake on 0x0A0  |  confidence 0.94  |  severity critical",
                                 "#EF4444", size=15))

        # Traffic table.
        table = QTableWidget(len(ROWS), 5)
        table.setHorizontalHeaderLabels(["timestamp", "can_id", "dlc", "data_hex", "status"])
        for r, row in enumerate(ROWS):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                # Highlight rows that have an alert status.
                if c == 4 and value == "ALERT":
                    item.setForeground(QColor("#EF4444"))
                table.setItem(r, c, item)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)   # read-only
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        page.addWidget(table)

        self.setCentralWidget(root)


if __name__ == "__main__":
    app = QApplication(sys.argv)                # one QApplication per program
    app.setStyleSheet(STYLE)
    window = Dashboard()
    window.show()
    sys.exit(app.exec())                        # event loop runs until the window closes