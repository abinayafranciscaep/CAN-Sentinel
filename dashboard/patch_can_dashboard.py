from pathlib import Path
import shutil
import sys

TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('dashboard/dashboard_mockup.py')
if not TARGET.is_file():
    raise SystemExit(f'Cannot find dashboard file: {TARGET.resolve()}')

source = TARGET.read_text(encoding='utf-8')
if 'class VehicleThreatWidget(QWidget):' in source:
    raise SystemExit('Vehicle threat visualization already appears to be installed; no changes made.')


def replace_once(old, new, label):
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'Expected exactly one anchor for {label}, found {count}. No changes written.')
    source = source.replace(old, new, 1)

# Add a JSONL loader that keeps the complete alert history for severity totals.
replace_once(
'''def find_recording(data_dir):
''',
'''def load_alerts(path):
    """Load every valid alert record from the detector JSONL file."""
    alerts = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict) or not REQUIRED_ALERT_FIELDS <= item.keys():
                    continue
                try:
                    item = dict(item)
                    item["confidence"] = float(item["confidence"])
                except (TypeError, ValueError, KeyError):
                    continue
                alerts.append(item)
    except OSError:
        return []
    return alerts


def find_recording(data_dir):
''',
'load_alerts insertion')

# Add a small interactive vehicle schematic before the main window class.
replace_once(
'''class Dashboard(QMainWindow):
''',
'''class VehicleThreatWidget(QWidget):
    """Simple top-down vehicle schematic; highlights the latest alert's ECU zone."""

    system_clicked = pyqtSignal(str)

    ZONES = {
        "brake": ("0x0A0", "Brake system"),
        "steering": ("0x0B0", "Steering"),
        "engine": ("0x100", "Engine RPM"),
        "speed": ("0x200", "Vehicle speed"),
        "temperature": ("0x300", "Engine temperature"),
        "infotainment": ("0x600", "Infotainment"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest_alert = None
        self.zone_rects = {}
        self.setMinimumHeight(245)
        self.setMinimumWidth(300)
        self.setToolTip("Highlighted areas are subsystem associations based on CAN ID, not physical fault localization.")

    @staticmethod
    def _zone_for_alert(alert):
        if not alert:
            return None
        can_id = str(alert.get("suspect_id", "")).strip().lower()
        mapping = {
            "0x0a0": "brake", "0x0b0": "steering", "0x100": "engine",
            "0x200": "speed", "0x300": "temperature", "0x600": "infotainment",
        }
        if can_id in mapping:
            return mapping[can_id]
        system = str(alert.get("affected_system", "")).lower()
        for key in ("brake", "steer", "engine", "speed", "temp", "infotainment"):
            if key in system:
                return {"steer": "steering", "temp": "temperature"}.get(key, key)
        return None

    def set_alerts(self, alerts):
        self.latest_alert = alerts[-1] if alerts else None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0B1727"))
        w, h = self.width(), self.height()
        cx = w * 0.50
        car_w = min(w * 0.34, 170)
        car_h = h * 0.82
        left, top = cx - car_w / 2, (h - car_h) / 2
        body = QRectF(left, top, car_w, car_h)

        # Wheels and vehicle body.
        wheel_w, wheel_h = car_w * 0.16, car_h * 0.19
        wheel_positions = [
            (left - wheel_w * .35, top + car_h * .19),
            (left + car_w - wheel_w * .65, top + car_h * .19),
            (left - wheel_w * .35, top + car_h * .67),
            (left + car_w - wheel_w * .65, top + car_h * .67),
        ]
        for x, y in wheel_positions:
            p.setPen(QPen(QColor("#52677F"), 1))
            p.setBrush(QColor("#172334"))
            p.drawRoundedRect(QRectF(x, y, wheel_w, wheel_h), 5, 5)
        p.setPen(QPen(QColor("#6E8AA8"), 2))
        p.setBrush(QColor("#142A40"))
        p.drawRoundedRect(body, car_w * .22, car_w * .22)

        # Glass/cabin and front/rear details.
        p.setPen(QPen(QColor("#34516D"), 1.5))
        p.setBrush(QColor("#203D58"))
        p.drawRoundedRect(QRectF(left + car_w*.17, top + car_h*.25, car_w*.66, car_h*.48), 16, 16)
        p.setBrush(QColor("#10243A"))
        p.drawRoundedRect(QRectF(left + car_w*.20, top + car_h*.29, car_w*.60, car_h*.16), 8, 8)
        p.drawRoundedRect(QRectF(left + car_w*.20, top + car_h*.54, car_w*.60, car_h*.15), 8, 8)
        p.setPen(QColor("#9FB4CE"))
        p.drawText(QRectF(left, top - 18, car_w, 16), Qt.AlignmentFlag.AlignCenter, "FRONT")

        zone = self._zone_for_alert(self.latest_alert)
        severity = str((self.latest_alert or {}).get("severity", "medium")).lower()
        color = QColor(severity_color(severity))
        self.zone_rects = {
            "engine": QRectF(left + car_w*.18, top + car_h*.06, car_w*.64, car_h*.16),
            "steering": QRectF(left + car_w*.25, top + car_h*.25, car_w*.50, car_h*.13),
            "speed": QRectF(left + car_w*.34, top + car_h*.40, car_w*.32, car_h*.10),
            "infotainment": QRectF(left + car_w*.28, top + car_h*.52, car_w*.44, car_h*.12),
            "temperature": QRectF(left + car_w*.58, top + car_h*.08, car_w*.22, car_h*.12),
            "brake": [
                 QRectF(x, y, wheel_w, wheel_h)
                    for x, y in wheel_positions
                ],
        }
        if zone:
            rects = self.zone_rects.get(zone, [])
            if not isinstance(rects, list):
                rects = [rects]

            for rect in rects:
                for pad, alpha, width in ((6, 35, 6), (3, 65, 3), (1, 100, 2)):
                    p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), alpha), width))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(rect.adjusted(-pad, -pad, pad, pad), 5, 5)

                p.setPen(QPen(color, 2))
                p.setBrush(QColor(color.red(), color.green(), color.blue(), 75))
                p.drawRoundedRect(rect, 5, 5)
        legend_x = min(w * .73, cx + car_w*.65)
        legend_y = max(24, top + 8)
        p.setFont(QFont(self.font().family(), 9))
        for key, (_, label) in self.ZONES.items():
            active = key == zone
            p.setPen(QColor(color if active else QColor("#8EA6C2")))
            prefix = "● " if active else "○ "
            p.drawText(int(legend_x), int(legend_y), prefix + label)
            legend_y += 25
        if self.latest_alert:
            cid = str(self.latest_alert.get("suspect_id", "Unknown"))
            p.setPen(color)
            p.drawText(10, h - 10, f"LATEST: {cid}  |  {severity.upper()}")
        else:
            p.setPen(QColor("#8EA6C2"))
            p.drawText(10, h - 10, "NO DETECTOR ALERT LOADED")
        p.end()

    def mousePressEvent(self, event):
        if not self.latest_alert:
            return
        zone = self._zone_for_alert(self.latest_alert)
        if zone:
            self.system_clicked.emit(zone)


class Dashboard(QMainWindow):
''',
'vehicle widget class')

# Add the visual panel immediately below the latest-alert banner.
replace_once(
'''        page.addWidget(alert_card)

        # ---------------- Recent CAN traffic: graph + minimised table ----------------
''',
'''        page.addWidget(alert_card)

        # ---------------- Live severity totals + vehicle threat map ----------------
        threat_map_card = QFrame()
        threat_map_card.setObjectName("trafficCard")
        threat_map_layout = QVBoxLayout(threat_map_card)
        threat_map_layout.setContentsMargins(14, 12, 14, 12)
        threat_map_layout.setSpacing(8)
        threat_map_heading = QLabel("LIVE VEHICLE THREAT MAP")
        threat_map_heading.setStyleSheet("color:#E8F2FF;font-size:14px;font-weight:bold;")
        threat_map_layout.addWidget(threat_map_heading)

        severity_row = QHBoxLayout()
        severity_row.setSpacing(8)
        self.severity_cards = {}
        for severity_name, severity_hex in (("critical", "#FF5A66"), ("high", "#FF8A4D"), ("medium", "#FFB547"), ("low", "#35E58B")):
            severity_card = make_card(severity_name.title() + " alerts", "0", severity_hex, size=22)
            self.severity_cards[severity_name] = severity_card
            severity_row.addWidget(severity_card)
        threat_map_layout.addLayout(severity_row)

        self.vehicle_widget = VehicleThreatWidget()
        self.vehicle_widget.system_clicked.connect(self.show_vehicle_system_details)
        threat_map_layout.addWidget(self.vehicle_widget)
        self.vehicle_status_label = QLabel("Waiting for a live detector alert. Highlighting is based on CAN-ID-to-subsystem mapping.")
        self.vehicle_status_label.setObjectName("muted")
        self.vehicle_status_label.setWordWrap(True)
        threat_map_layout.addWidget(self.vehicle_status_label)
        page.addWidget(threat_map_card)

        # ---------------- Recent CAN traffic: graph + minimised table ----------------
''',
'vehicle panel insertion')

# Replace refresh_alerts with a version that updates counts, vehicle map, and multiline details.
start = source.find('    def refresh_alerts(self):\n')
end = source.find('    def quarantine_latest_alert(self):\n', start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate refresh_alerts method boundaries. No changes written.')
new_method = '''    def refresh_alerts(self):
        """Refresh severity totals and show the newest live detector alert."""
        global ALERT
        alerts = load_alerts(ALERT_FILE)
        counts = Counter(str(item.get("severity", "unknown")).lower() for item in alerts)
        for severity_name, card in getattr(self, "severity_cards", {}).items():
            card.value_label.setText(str(counts.get(severity_name, 0)))
        if hasattr(self, "vehicle_widget"):
            self.vehicle_widget.set_alerts(alerts)
        if not alerts:
            if hasattr(self, "vehicle_status_label"):
                self.vehicle_status_label.setText("No detector alerts in the live alert log. No vehicle region is highlighted.")
            return

        latest = alerts[-1]
        if hasattr(self, "vehicle_status_label"):
            self.vehicle_status_label.setText(
                f"Latest finding: {latest.get('attack_type', 'Unknown')} on "
                f"{latest.get('suspect_id', 'Unknown')} · "
                f"{str(latest.get('severity', 'unknown')).upper()} · "
                f"{latest.get('affected_system', 'Unknown')}. "
                "Subsystem glow is a CAN-ID mapping, not physical fault localization."
            )
        if latest == ALERT:
            return

        ALERT = latest
        self.alert_summary = (
            "LIVE DETECTOR ALERT — RULES-BASED FINDING\\n"
            f"Source: {ALERT_FILE.name}\\n"
            "Verification: Live CAN stream; rule-based detection (not ML-confirmed)\\n\\n"
            f"Type: {latest.get('attack_type', 'Unknown')}\\n"
            f"CAN ID: {latest.get('suspect_id', 'Unknown')}\\n"
            f"Severity: {latest.get('severity', 'Unknown')}\\n"
            f"Confidence: {latest.get('confidence', 0):.2f}\\n"
            f"Affected system: {latest.get('affected_system', 'Unknown')}\\n"
            f"Detection layer: {latest.get('detection_layer', 'Unknown')}\\n"
            f"Technique: {latest.get('technique', 'Unknown')}"
        )
        self.alert_details.setText(self.alert_summary)
        if hasattr(self, "alert_banner_detail"):
            e = html.escape
            sev = str(latest.get("severity", "unknown"))
            sev_col = severity_color(sev)
            self.alert_banner_detail.setText(
                f'<span style="color:#FF5A66;font-weight:bold;">'
                f'{e(str(latest.get("attack_type", "Unknown")))} on '
                f'{e(str(latest.get("suspect_id", "Unknown")))}</span>'
                f'<span style="color:#DCE8F7;">  |  '
                f'confidence {float(latest.get("confidence", 0)):.2f}  |  '
                f'{e(str(latest.get("affected_system", "Unknown")))}  |  '
                f'severity </span>'
                f'<span style="color:{sev_col};font-weight:bold;">{e(sev)}</span>'
            )
        self.review_button.setEnabled(True)
        self.alert_quarantine_button.setEnabled(True)

    def show_vehicle_system_details(self, system):
        """Show which latest alert is associated with the selected vehicle zone."""
        alerts = load_alerts(ALERT_FILE)
        matches = [item for item in alerts if VehicleThreatWidget._zone_for_alert(item) == system]
        if not matches:
            self.vehicle_status_label.setText(f"{system.title()}: no matching detector alert in the current log.")
            return
        item = matches[-1]
        self.vehicle_status_label.setText(
            f"{system.title()} · CAN ID {item.get('suspect_id', 'Unknown')} · "
            f"{item.get('attack_type', 'Unknown')} · "
            f"{str(item.get('severity', 'unknown')).upper()} · "
            f"Confidence {float(item.get('confidence', 0)):.2f}"
        )
        self.go_to(self.TAB_ALERTS)

'''
source = source[:start] + new_method + source[end:]

backup = TARGET.with_name(TARGET.name + '.before_vehicle_map')
if backup.exists():
    raise SystemExit(f'Backup already exists: {backup}. Rename it before retrying; no changes written.')
shutil.copy2(TARGET, backup)
TARGET.write_text(source, encoding='utf-8', newline='\n')
print(f'Updated: {TARGET.resolve()}')
print(f'Backup:  {backup.resolve()}')
print('Next: run python3 -m py_compile dashboard/dashboard_mockup.py')
