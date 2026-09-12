import math
import sys
import json
import re
import requests
from pathlib import Path
import airportsdata

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView

AIRPORTS_DB = airportsdata.load('ICAO')

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
MY_LAT = 51.471537
MY_LON = -0.334237
RADIUS_NM = 30
DEFAULT_ZOOM = 9

SVG_FOLDER = Path(r"C:\Users\lol42\Downloads\Shapes SVG").resolve()
ICON_SOLID_COLOR = "#FFD700"  # Bright Gold

HEADERS = {
    "User-Agent": "ADSBMapTracker/28.0",
    "Accept": "application/json"
}

LAST_KNOWN_HEADINGS = {}
SVG_CACHE = {}

# Set of common helicopter ICAO designators to automatically map to H60
HELICOPTER_TYPES = {
    "R44", "R22", "R66", "EC35", "EC45", "EC30", "EC20", "EC55", 
    "B06", "B206", "B407", "B412", "B429", "H60", "S76", "S92", 
    "A109", "A119", "AW139", "AW169", "AW189", "AS50", "AS55", 
    "AS65", "BK11", "HU50", "MD50", "CABRI", "G2"
}

FALLBACK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">
    <path fill="{ICON_SOLID_COLOR}" stroke="#000000" stroke-width="2" d="M 50 3.5 C 48 3.5 46.5 7 46.1 14.4 L 46.1 39.4 L 4.3 61.7 L 9.2 64 L 46.1 53.9 L 46.1 81.6 L 33.6 93.3 L 50 90.2 L 66.4 93.3 L 53.9 81.6 L 53.9 53.9 L 95.7 61.7 L 53.9 39.4 L 53.9 14.4 Z"/>
</svg>"""

def sanitize_svg_code(svg_text):
    """
    Strips opacities and forces all paths/shapes inside the SVG to solid gold with a thin black outline.
    """
    svg_text = re.sub(r'opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'fill-opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke-opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'style=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    
    svg_text = re.sub(r'fill=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke-width=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)

    # Adds stroke="#000000" and stroke-width="1.5" for a thin black outline
    svg_text = re.sub(
        r'<(path|polygon|rect|circle|g)\b',
        rf'<\1 fill="{ICON_SOLID_COLOR}" stroke="#000000" stroke-width="1" stroke-linejoin="round" ',
        svg_text,
        flags=re.IGNORECASE
    )
    
    if "<svg" in svg_text:
        svg_text = svg_text.replace("<svg", f'<svg fill="{ICON_SOLID_COLOR}" width="100%" height="100%" ', 1)

    return " ".join(svg_text.split())

def preload_svgs():
    """Preloads and sanitizes all local SVG files."""
    SVG_CACHE["DEFAULT"] = sanitize_svg_code(FALLBACK_SVG)

    if SVG_FOLDER.exists():
        for file in SVG_FOLDER.glob("*.svg"):
            try:
                raw_text = file.read_text(encoding="utf-8", errors="ignore")
                clean_svg = sanitize_svg_code(raw_text)
                
                key = file.stem.upper().strip()
                SVG_CACHE[key] = clean_svg
            except Exception as e:
                print(f"Error reading {file.name}: {e}")
    else:
        print(f"Warning: Folder not found at {SVG_FOLDER}")

def get_svg_string(actype, category=""):
    clean = str(actype).strip().upper()
    cat = str(category).strip().upper()
    
    # 1. Map A319 to a19n.svg
    if clean == "A319":
        clean = "A19N"
    
    # 2. Map all helicopters to H60.svg (via category 'A7' or designator list)
    if cat == "A7" or clean in HELICOPTER_TYPES or "HELI" in clean or clean.startswith("H"):
        clean = "H60"

    # Direct match
    if clean in SVG_CACHE:
        return SVG_CACHE[clean]
    
    # Partial match fallback
    for key, code in SVG_CACHE.items():
        if clean in key or key in clean:
            return code
            
    return SVG_CACHE["DEFAULT"]

# -------------------------------------------------------------
# DATA HELPERS
# -------------------------------------------------------------
def get_airport_name(code):
    if not code or code == "N/A": return "N/A"
    clean_code = str(code).strip().upper()
    if clean_code in AIRPORTS_DB:
        ap = AIRPORTS_DB[clean_code]
        return f"{ap['name']} ({clean_code})"
    return clean_code

def haversine_nm(lat1, lon1, lat2, lon2):
    r = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def extract_heading(plane, hex_code):
    for key in ("true_heading", "mag_heading", "track", "dir", "heading", "nav_heading"):
        val = plane.get(key)
        if val is not None and str(val) != "N/A":
            try:
                heading_val = float(val)
                if heading_val != 0 or hex_code not in LAST_KNOWN_HEADINGS:
                    LAST_KNOWN_HEADINGS[hex_code] = heading_val
                return heading_val
            except ValueError:
                pass
    return LAST_KNOWN_HEADINGS.get(hex_code, 0.0)

class DataFetchThread(QThread):
    data_ready = pyqtSignal(dict)

    def run(self):
        result = {"aircraft": [], "closest_plane": None, "route": ("N/A", "N/A"), "trace": []}
        endpoints = [
            f"https://opendata.adsb.fi/api/v3/lat/{MY_LAT}/lon/{MY_LON}/dist/{RADIUS_NM}",
            f"https://api.adsb.lol/v2/lat/{MY_LAT}/lon/{MY_LON}/dist/{RADIUS_NM}"
        ]

        aircraft_list = []
        for url in endpoints:
            try:
                res = requests.get(url, headers=HEADERS, timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    aircraft_list = data.get("ac", data.get("aircraft", []))
                    if aircraft_list: break
            except Exception:
                pass

        result["aircraft"] = aircraft_list

        min_dist = float("inf")
        closest = None
        for plane in aircraft_list:
            p_lat, p_lon = plane.get("lat"), plane.get("lon")
            if p_lat is not None and p_lon is not None:
                dist = haversine_nm(MY_LAT, MY_LON, p_lat, p_lon)
                if dist < min_dist:
                    min_dist = dist
                    closest = plane

        if closest:
            result["closest_plane"] = closest
            hex_code = str(closest.get("hex", "")).lower()
            callsign = str(closest.get("flight", "")).strip()

            try:
                t_res = requests.get(f"https://opendata.adsb.fi/api/v2/trace/{hex_code}", headers=HEADERS, timeout=3)
                if t_res.status_code == 200:
                    trace_pts = t_res.json().get("trace", [])
                    result["trace"] = [[pt[1], pt[2]] for pt in trace_pts if len(pt) >= 3 and pt[1] and pt[2]]
            except Exception:
                pass

            if callsign and callsign not in ["UNKNOWN", "N/A"]:
                try:
                    r_res = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", headers=HEADERS, timeout=2)
                    if r_res.status_code == 200:
                        r_data = r_res.json().get("response", {}).get("flightroute", {})
                        orig = r_data.get("origin", {}).get("icao_code", "N/A")
                        dest = r_data.get("destination", {}).get("icao_code", "N/A")
                        result["route"] = (orig, dest)
                except Exception:
                    pass

        self.data_ready.emit(result)

BASE_MAP_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map {{ height: 100%; width: 100%; margin: 0; background: #121212; overflow: hidden; }}
        .leaflet-div-icon {{ background: transparent !important; border: none !important; }}
        .aircraft-wrapper {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            filter: drop-shadow(0px 0px 2px #000) drop-shadow(0px 2px 4px rgba(0,0,0,0.9));
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{MY_LAT}, {MY_LON}], {DEFAULT_ZOOM});
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ maxZoom: 18 }}).addTo(map);

        L.circleMarker([{MY_LAT}, {MY_LON}], {{ radius: 6, color: '#FFF', fillColor: '#FF007F', fillOpacity: 1 }}).bindTooltip("Monitoring Location").addTo(map);

        var aircraftMarkers = {{}};
        var leadLine = null, trailLine = null;

        function updateMapData(aircraftList, closestHex, closestTrace) {{
            var active = {{}};

            aircraftList.forEach(function(p) {{
                active[p.hex] = true;
                var isClosest = (p.hex === closestHex);
                var size = isClosest ? 40 : 30;

                var html = '<div class="aircraft-wrapper" style="transform: rotate(' + p.heading + 'deg);">' + p.svgCode + '</div>';

                var icon = L.divIcon({{ html: html, iconSize: [size, size], iconAnchor: [size/2, size/2] }});
                var tooltip = p.callsign + ' [' + p.actype + '] (' + p.dist.toFixed(1) + ' NM)';

                if (aircraftMarkers[p.hex]) {{
                    aircraftMarkers[p.hex].setLatLng([p.lat, p.lon]);
                    aircraftMarkers[p.hex].setIcon(icon);
                    aircraftMarkers[p.hex].setTooltipContent(tooltip);
                }} else {{
                    aircraftMarkers[p.hex] = L.marker([p.lat, p.lon], {{ icon: icon }}).bindTooltip(tooltip).addTo(map);
                }}

                if (isClosest) {{
                    var lineCoords = [[{MY_LAT}, {MY_LON}], [p.lat, p.lon]];
                    if (leadLine) leadLine.setLatLngs(lineCoords);
                    else leadLine = L.polyline(lineCoords, {{ color: '#FF007F', weight: 2, dashArray: '5,5' }}).addTo(map);
                }}
            }});

            for (var hex in aircraftMarkers) {{
                if (!active[hex]) {{ map.removeLayer(aircraftMarkers[hex]); delete aircraftMarkers[hex]; }}
            }}

            if (closestHex && closestTrace && closestTrace.length >= 2) {{
                if (trailLine) trailLine.setLatLngs(closestTrace);
                else trailLine = L.polyline(closestTrace, {{ color: '#FF007F', weight: 3 }}).addTo(map);
            }} else if (trailLine) {{
                map.removeLayer(trailLine); trailLine = null;
            }}
        }}
    </script>
</body>
</html>
"""

class SatelliteMapTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        preload_svgs()

        self.setWindowTitle("Satellite ADSB Aircraft Tracker")
        self.setGeometry(100, 100, 1200, 750)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.data_panel = QWidget()
        self.data_panel.setFixedWidth(320)
        self.data_panel.setStyleSheet("background-color: #121212; color: #FFFFFF;")
        panel_layout = QVBoxLayout(self.data_panel)

        title = QLabel("TRACKED AIRCRAFT")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FF007F;")
        panel_layout.addWidget(title)

        self.info_labels = {}
        fields = ["callsign", "actype", "registration", "origin", "destination", "distance", "hex", "alt", "speed", "heading"]
        for key in fields:
            t = QLabel(key.upper())
            t.setStyleSheet("font-size: 10px; color: #888888;")
            v = QLabel("--")
            v.setStyleSheet("font-size: 12px; font-weight: bold;")
            panel_layout.addWidget(t)
            panel_layout.addWidget(v)
            self.info_labels[key] = v

        panel_layout.addStretch()
        main_layout.addWidget(self.data_panel)

        self.web_view = QWebEngineView()
        main_layout.addWidget(self.web_view)
        self.web_view.setHtml(BASE_MAP_HTML)

        self.fetch_thread = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_async_update)
        self.timer.start(5000)
        self.start_async_update()

    def start_async_update(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            return
        self.fetch_thread = DataFetchThread()
        self.fetch_thread.data_ready.connect(self.handle_data_ready)
        self.fetch_thread.start()

    def handle_data_ready(self, data):
        aircraft_list = data.get("aircraft", [])
        closest = data.get("closest_plane")
        route = data.get("route", ("N/A", "N/A"))
        trace = data.get("trace", [])

        formatted = []
        for p in aircraft_list:
            lat, lon = p.get("lat"), p.get("lon")
            if lat is None or lon is None: continue
            p_hex = str(p.get("hex", "N/A")).upper()
            actype = str(p.get("t", "MEDIUM")).upper().strip()
            category = str(p.get("category", "")).strip().upper()
            
            formatted.append({
                "hex": p_hex, "lat": lat, "lon": lon,
                "callsign": str(p.get("flight", "N/A")).strip(),
                "actype": actype,
                "svgCode": get_svg_string(actype, category),
                "heading": extract_heading(p, p_hex),
                "dist": haversine_nm(MY_LAT, MY_LON, lat, lon)
            })

        closest_hex = str(closest.get("hex", "")).upper() if closest else ""
        self.web_view.page().runJavaScript(f"updateMapData({json.dumps(formatted)}, '{closest_hex}', {json.dumps(trace)});")

        if not closest:
            for l in self.info_labels.values(): l.setText("--")
            return

        self.info_labels["callsign"].setText(str(closest.get("flight", "UNKNOWN")).strip())
        self.info_labels["actype"].setText(str(closest.get("t", "N/A")))
        self.info_labels["registration"].setText(str(closest.get("r", "N/A")))
        self.info_labels["origin"].setText(get_airport_name(route[0]))
        self.info_labels["destination"].setText(get_airport_name(route[1]))
        dist = haversine_nm(MY_LAT, MY_LON, closest.get("lat"), closest.get("lon"))
        self.info_labels["distance"].setText(f"{dist:.2f} NM")
        self.info_labels["hex"].setText(closest_hex)
        self.info_labels["alt"].setText(f"{closest.get('alt_baro', 'N/A')} ft")
        self.info_labels["speed"].setText(f"{closest.get('gs', 'N/A')} kts")
        self.info_labels["heading"].setText(f"{extract_heading(closest, closest_hex):.1f}°")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SatelliteMapTracker()
    win.show()
    sys.exit(app.exec())