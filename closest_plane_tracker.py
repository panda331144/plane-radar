import math
import sys
import json
import re
import requests
from pathlib import Path
from collections import defaultdict
import airportsdata

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QComboBox, QPushButton)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

AIRPORTS_DB = airportsdata.load('ICAO')

# -------------------------------------------------------------
# TOP 10 BUSIEST AIRPORTS IN THE WORLD (ICAO Data)
# -------------------------------------------------------------
BUSIEST_AIRPORTS = [
    ("KATL - Atlanta Hartsfield-Jackson", "KATL"),
    ("OMDB - Dubai International", "OMDB"),
    ("RJTT - Tokyo Haneda", "RJTT"),
    ("KDFW - Dallas/Fort Worth", "KDFW"),
    ("ZSPD - Shanghai Pudong", "ZSPD"),
    ("KORD - Chicago O'Hare", "KORD"),
    ("EGLL - London Heathrow", "EGLL"),
    ("LTFM - Istanbul Airport", "LTFM"),
    ("ZGGG - Guangzhou Baiyun", "ZGGG"),
    ("KDEN - Denver International", "KDEN")
]

# -------------------------------------------------------------
# RUNWAY APPROACHES & THRESHOLDS
# -------------------------------------------------------------
CUSTOM_RUNWAY_APPROACHES = [
    # London Heathrow
    ("LHR 27 APP", "51.471537,-0.334237"),
    ("LHR 09 APP", "51.469687,-0.550237"),

    # JFK - John F. Kennedy International
    ("KJFK RWY 22L", "40.716717,-73.697983"),
    ("KJFK RWY 22R", "40.722000,-73.706433"),
    ("KJFK RWY 13L", "40.700667,-73.882050"),

    # IAH - George Bush Intercontinental
    ("KIAH RWY 26L", "29.993433,-95.229850"),
    ("KIAH RWY 26R", "30.007183,-95.234917"),
    ("KIAH RWY 27",  "29.977617,-95.207117"),

    # LGA - LaGuardia Airport
    ("KLGA RWY 22",  "40.856033,-73.811967"),
    ("KLGA RWY 31",  "40.727833,-73.763800"),
]

# -------------------------------------------------------------
# AIRLINE ICAO LOOKUP DICTIONARY
# -------------------------------------------------------------
AIRLINES_DB = {
    "AAL": "American Airlines", "AAR": "Asiana Airlines", "ABD": "Air Atlanta Icelandic",
    "ABL": "Air Busan", "ABR": "ASL Airlines Ireland", "ACA": "Air Canada",
    "ACI": "Aircalin", "AEA": "Air Europa", "AEE": "Aegean Airlines",
    "AFL": "Aeroflot", "AFR": "Air France", "AHY": "Azerbaijan Airlines",
    "AIC": "Air India", "AIZ": "Arkia Israeli Airlines", "AKX": "ANA Wings",
    "ALD": "Air Leisure", "ALY": "El Al Israel Airlines", "AMC": "Air Malta",
    "ANA": "All Nippon Airways", "ANS": "Andes Líneas Aéreas", "AOJ": "Avangard Aviation",
    "APG": "Air France Hop", "APN": "Air Nippon", "ARA": "Arik Air",
    "ARE": "LATAM Airlines Colombia", "ARG": "Aerolíneas Argentinas", "ASA": "Alaska Airlines",
    "ASL": "Air Serbia", "ASY": "Australian Air Force", "AUA": "Austrian Airlines",
    "AVA": "Avianca", "AWE": "US Airways", "AXM": "AirAsia",
    "AZA": "ITA Airways / Alitalia", "AZU": "Azul Brazilian Airlines", "BAW": "British Airways",
    "BCH": "Binter Canarias", "BED": "Belgrade Flight School", "BER": "Air Berlin",
    "BFR": "Burkina Airlines", "BGB": "Binter Canarias", "BKP": "Bangkok Airways",
    "BLX": "TUI Airways Nordic", "BMA": "BMI Regional", "BMI": "bmi",
    "BOS": "La Compagnie", "BPA": "Blue Panorama Airlines", "BRT": "British Regional Airlines",
    "BTI": "airBaltic", "BTP": "Balkan Holidays Air", "BUC": "European Air Charter",
    "BUS": "BinAir", "CBY": "Camair-Co", "CCA": "Air China",
    "CEB": "Cebu Pacific", "CES": "China Eastern Airlines", "CFG": "Condor",
    "CHA": "Bizjet Aviation", "CHF": "Swiss Air Force", "CHH": "Hainan Airlines",
    "CIM": "Cimber Air", "CLX": "Cargolux", "CMP": "Copa Airlines",
    "CNA": "Canair", "CNE": "CanJet", "CPA": "Cathay Pacific",
    "CPN": "Caspian Airlines", "CSA": "Czech Airlines", "CSN": "China Southern Airlines",
    "CSH": "Shanghai Airlines", "CTN": "Croatia Airlines", "CUB": "Cubana de Aviación",
    "CYP": "Cyprus Airways", "DAL": "Delta Air Lines", "DAN": "Dan Air",
    "DCM": "DHL Aviation", "DLH": "Lufthansa", "DTR": "DAT Danish Air Transport",
    "EDW": "Edelweiss Air", "EIN": "Aer Lingus", "EJU": "easyJet Europe",
    "ELA": "Cello Aviation", "ELY": "El Al Israel Airlines", "UAE": "Emirates",
    "EGF": "American Eagle", "ETH": "Ethiopian Airlines", "ETD": "Etihad Airways",
    "EVA": "EVA Air", "EWG": "Eurowings", "EZY": "easyJet",
    "EZS": "easyJet Switzerland", "FDX": "FedEx Express", "FIN": "Finnair",
    "FJI": "Fiji Airways", "FMY": "French Air Force", "FPO": "ASL Airlines France",
    "FWI": "Air Caraïbes", "GAO": "Golden Air", "GFA": "Gulf Air",
    "GIA": "Garuda Indonesia", "GTI": "Atlas Air", "HAL": "Hawaiian Airlines",
    "HFY": "Hi Fly", "HDA": "Cathay Dragon", "HVN": "Vietnam Airlines",
    "IBE": "Iberia", "IBS": "Iberia Express", "ICE": "Icelandair",
    "IGO": "IndiGo", "ISR": "Israir Airlines", "JAF": "TUI fly Belgium",
    "JAL": "Japan Airlines", "JAT": "Air Serbia", "JBA": "Helijet",
    "JBU": "JetBlue Airways", "JST": "Jetstar Airways", "KAC": "Kuwait Airways",
    "KAL": "Korean Air", "KLM": "KLM Royal Dutch Airlines", "KMC": "Kawasaki Heavy Industries",
    "KNE": "Flynas", "KQA": "Kenya Airways", "LAN": "LATAM Chile",
    "LOG": "Loganair", "LOT": "LOT Polish Airlines", "LRC": "Avianca Costa Rica",
    "LTE": "LTE International Airways", "LTU": "LTU International", "LVG": "Livingston",
    "LZB": "Bulgaria Air", "MAA": "MasAir", "MAC": "Air Arabia",
    "MAH": "Malev Hungarian Airlines", "MAS": "Malaysia Airlines", "MAU": "Air Mauritius",
    "MDW": "Midway Airlines", "MEA": "Middle East Airlines", "MES": "Mesaba Airlines",
    "MGL": "MIAT Mongolian Airlines", "MPH": "Martinair", "MSR": "EgyptAir",
    "NAX": "Norwegian Air Shuttle", "NKS": "Spirit Airlines", "NLY": "Niki",
    "NNO": "Norte Air", "NOK": "Nok Air", "NVR": "Novair",
    "OAL": "Olympic Air", "OMA": "Oman Air", "OAE": "Omni Air International",
    "PAC": "Polar Air Cargo", "PAL": "Philippine Airlines", "PIA": "Pakistan International Airlines",
    "PLN": "Aero VIP", "QFA": "Qantas", "QTR": "Qatar Airways",
    "RAM": "Royal Air Maroc", "RAR": "Air Rarotonga", "RBA": "Royal Brunei Airlines",
    "REA": "Aer Lingus Regional", "RGL": "Regional Air Lines", "RIT": "Asian Air",
    "RJU": "Rooster Aviation", "RNA": "Nepal Airlines", "ROU": "Air Canada Rouge",
    "RPA": "Republic Airways", "RRA": "Royal Air Freight", "RRE": "Reach Air Medical Services",
    "RSO": "Aero Sahara", "RSR": "Air Spruns", "RWD": "RwandAir",
    "RYR": "Ryanair", "SAA": "South African Airways", "SAS": "Scandinavian Airlines (SAS)",
    "SAT": "SATA Air Açores", "SAY": "ScotAirways", "SIA": "Singapore Airlines",
    "SBA": "Aero VIP", "SDA": "Solinair", "SEY": "Air Seychelles",
    "SHT": "British Airways Shuttle", "SIL": "Air Senegal", "SKW": "SkyWest Airlines",
    "SLK": "SilkAir", "SNA": "Senator Aviation Services", "SUD": "Sudan Airways",
    "SVA": "Saudia", "SWR": "Swiss International Air Lines", "TAM": "LATAM Brasil",
    "TAP": "TAP Air Portugal", "TAR": "Tunisair", "TFL": "TUI fly Netherlands",
    "TGW": "Scoot", "THA": "Thai Airways", "THY": "Turkish Airlines",
    "TOM": "TUI Airways", "TRA": "Transavia", "TRS": "AirTran Airways",
    "TSC": "Air Transat", "TVF": "Transavia France", "UAL": "United Airlines",
    "UPS": "UPS Airlines", "UTA": "UTair Aviation", "VIR": "Virgin Atlantic",
    "VOZ": "Virgin Australia", "VLG": "Vueling Airlines", "VTE": "Volotea",
    "WZZ": "Wizz Air", "XAX": "AirAsia X"
}

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
MY_LAT = 51.471537
MY_LON = -0.334237
RADIUS_NM = 30
DEFAULT_ZOOM = 9

POSITION_HISTORY = defaultdict(list)
MAX_HISTORY_POINTS = 100

SVG_FOLDER = Path(r"C:\Users\lol42\Downloads\Shapes SVG").resolve()
ICON_SOLID_COLOR = "#FFD700"  # Bright Gold

HEADERS = {
    "User-Agent": "ADSBMapTracker/28.0",
    "Accept": "application/json"
}

LAST_KNOWN_HEADINGS = {}
SVG_CACHE = {}

HELICOPTER_TYPES = {
    "R44", "R22", "R66", "EC35", "EC45", "EC30", "EC20", "EC55", 
    "B06", "B206", "B407", "B412", "B429", "H60", "S76", "S92", 
    "A109", "A119", "AW139", "AW169", "AW189", "AS50", "AS55", 
    "AS65", "BK11", "HU50", "MD50", "CABRI", "G2"
}

FALLBACK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">
    <path fill="{ICON_SOLID_COLOR}" stroke="#000000" stroke-width="2" d="M 50 3.5 C 48 3.5 46.5 7 46.1 14.4 L 46.1 39.4 L 4.3 61.7 L 9.2 64 L 46.1 53.9 L 46.1 81.6 L 33.6 93.3 L 53.9 81.6 L 53.9 53.9 L 95.7 61.7 L 53.9 39.4 L 53.9 14.4 Z"/>
</svg>"""

def get_airline_name(callsign):
    if not callsign or callsign in ["UNKNOWN", "N/A"]:
        return "Unknown Airline"
    clean_callsign = str(callsign).strip().upper()
    prefix = clean_callsign[:3]
    return AIRLINES_DB.get(prefix, "Private / General Aviation")

def sanitize_svg_code(svg_text):
    svg_text = re.sub(r'opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'fill-opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke-opacity=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'style=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    
    svg_text = re.sub(r'fill=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)
    svg_text = re.sub(r'stroke-width=["\'][^"\']*["\']', '', svg_text, flags=re.IGNORECASE)

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

def get_svg_string(actype, category=""):
    clean = str(actype).strip().upper()
    cat = str(category).strip().upper()
    
    if clean == "A319": clean = "A19N"
    if cat == "A7" or clean in HELICOPTER_TYPES or "HELI" in clean or clean.startswith("H"):
        clean = "H60"

    if clean in SVG_CACHE: return SVG_CACHE[clean]
    for key, code in SVG_CACHE.items():
        if clean in key or key in clean: return code
            
    return SVG_CACHE["DEFAULT"]

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

    def __init__(self, lat, lon, selected_hex=None):
        super().__init__()
        self.lat = lat
        self.lon = lon
        self.selected_hex = selected_hex

    def run(self):
        result = {"aircraft": [], "tracked_plane": None, "closest_plane": None, "route": ("N/A", "N/A"), "trace": []}
        endpoints = [
            f"https://opendata.adsb.fi/api/v3/lat/{self.lat}/lon/{self.lon}/dist/{RADIUS_NM}",
            f"https://api.adsb.lol/v2/lat/{self.lat}/lon/{self.lon}/dist/{RADIUS_NM}"
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
        selected_plane = None

        for plane in aircraft_list:
            p_lat, p_lon = plane.get("lat"), plane.get("lon")
            p_hex = str(plane.get("hex", "")).upper()
            
            if p_lat is not None and p_lon is not None:
                coords = [p_lat, p_lon]
                if not POSITION_HISTORY[p_hex] or POSITION_HISTORY[p_hex][-1] != coords:
                    POSITION_HISTORY[p_hex].append(coords)
                    if len(POSITION_HISTORY[p_hex]) > MAX_HISTORY_POINTS:
                        POSITION_HISTORY[p_hex].pop(0)

                dist = haversine_nm(self.lat, self.lon, p_lat, p_lon)
                if dist < min_dist:
                    min_dist = dist
                    closest = plane
                if self.selected_hex and p_hex == self.selected_hex.upper():
                    selected_plane = plane

        result["closest_plane"] = closest
        tracked = selected_plane if selected_plane else closest
        result["tracked_plane"] = tracked

        if tracked:
            tracked_hex = str(tracked.get("hex", "")).lower()
            callsign = str(tracked.get("flight", "")).strip()

            api_trace_fetched = False
            try:
                trace_url = f"https://opendata.adsb.fi/api/v2/trace/{tracked_hex}"
                t_res = requests.get(trace_url, headers=HEADERS, timeout=4)
                if t_res.status_code == 200:
                    raw_trace = t_res.json().get("trace", [])
                    extracted_trace = [
                        [pt[1], pt[2]] for pt in raw_trace 
                        if len(pt) >= 3 and pt[1] is not None and pt[2] is not None
                    ]
                    if extracted_trace:
                        result["trace"] = extracted_trace
                        api_trace_fetched = True
            except Exception as e:
                print(f"Error fetching API trace: {e}")

            if not api_trace_fetched:
                result["trace"] = POSITION_HISTORY.get(tracked_hex.upper(), [])

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
            cursor: pointer !important;
            pointer-events: auto !important;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{MY_LAT}, {MY_LON}], {DEFAULT_ZOOM});
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ maxZoom: 18 }}).addTo(map);

        var centerMarker = L.circleMarker([{MY_LAT}, {MY_LON}], {{ radius: 6, color: '#FFF', fillColor: '#FF007F', fillOpacity: 1 }}).bindTooltip("Monitoring Location").addTo(map);

        var aircraftMarkers = {{}};
        var leadLine = null, trailLine = null;

        map.on('click', function(e) {{
            console.log('SELECT_HEX:CLEAR');
        }});

        function setMapCenter(lat, lon, label) {{
            map.setView([lat, lon], {DEFAULT_ZOOM});
            centerMarker.setLatLng([lat, lon]);
            centerMarker.setTooltipContent(label || "Monitoring Location");
        }}

        function updateMapData(aircraftList, trackedHex, trackedTrace, centerLat, centerLon) {{
            var active = {{}};

            aircraftList.forEach(function(p) {{
                active[p.hex] = true;
                var isTracked = (p.hex === trackedHex);
                var size = isTracked ? 44 : 30;

                var html = '<div class="aircraft-wrapper" style="transform: rotate(' + p.heading + 'deg);">' + p.svgCode + '</div>';

                var icon = L.divIcon({{ html: html, iconSize: [size, size], iconAnchor: [size/2, size/2] }});
                var tooltipText = p.callsign + ' [' + p.actype + '] (' + p.dist.toFixed(1) + ' NM)';

                if (aircraftMarkers[p.hex]) {{
                    aircraftMarkers[p.hex].setLatLng([p.lat, p.lon]);
                    aircraftMarkers[p.hex].setIcon(icon);
                    aircraftMarkers[p.hex].setTooltipContent(tooltipText);
                }} else {{
                    var marker = L.marker([p.lat, p.lon], {{ icon: icon, interactive: true }}).addTo(map);
                    marker.bindTooltip(tooltipText, {{ interactive: false }});
                    
                    (function(hexCode) {{
                        marker.on('click', function(e) {{
                            if (e && e.originalEvent) e.originalEvent.stopPropagation();
                            console.log('SELECT_HEX:' + hexCode);
                        }});
                    }})(p.hex);

                    aircraftMarkers[p.hex] = marker;
                }}

                if (isTracked) {{
                    var lineCoords = [[centerLat, centerLon], [p.lat, p.lon]];
                    if (leadLine) leadLine.setLatLngs(lineCoords);
                    else leadLine = L.polyline(lineCoords, {{ color: '#FF007F', weight: 2, dashArray: '5,5' }}).addTo(map);
                }}
            }});

            for (var hex in aircraftMarkers) {{
                if (!active[hex]) {{ map.removeLayer(aircraftMarkers[hex]); delete aircraftMarkers[hex]; }}
            }}

            if (trackedHex && trackedTrace && trackedTrace.length >= 2) {{
                var trailOptions = {{
                    color: '#00FF88',
                    weight: 3,
                    dashArray: null,
                    lineCap: 'round',
                    opacity: 0.95
                }};

                if (trailLine) {{
                    trailLine.setLatLngs(trackedTrace);
                    trailLine.setStyle(trailOptions);
                }} else {{
                    trailLine = L.polyline(trackedTrace, trailOptions).addTo(map);
                }}
            }} else if (trailLine) {{
                map.removeLayer(trailLine); 
                trailLine = null;
            }}
        }}
    </script>
</body>
</html>
"""

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, parent_tracker):
        super().__init__(parent_tracker)
        self.tracker = parent_tracker

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if "SELECT_HEX:" in message:
            target_hex = message.split("SELECT_HEX:")[1].strip()
            if target_hex == "CLEAR":
                self.tracker.on_plane_selected("")
            else:
                self.tracker.on_plane_selected(target_hex)

class SatelliteMapTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        preload_svgs()

        self.setWindowTitle("Satellite ADSB Aircraft Tracker")
        self.setGeometry(100, 100, 1200, 750)

        self.current_lat = MY_LAT
        self.current_lon = MY_LON
        self.selected_hex = None

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.data_panel = QWidget()
        self.data_panel.setFixedWidth(320)
        self.data_panel.setStyleSheet("background-color: #121212; color: #FFFFFF;")
        panel_layout = QVBoxLayout(self.data_panel)

        search_title = QLabel("MAP CENTER / AIRPORT SEARCH")
        search_title.setStyleSheet("font-size: 10px; color: #888888; font-weight: bold;")
        panel_layout.addWidget(search_title)

        self.combo_box = QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setStyleSheet("""
            QComboBox {
                background-color: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #333;
                padding: 4px;
                font-size: 11px;
            }
            QComboBox QAbstractItemView {
                background-color: #1A1A1A;
                color: #FFFFFF;
                selection-background-color: #FF007F;
            }
        """)
        
        # Custom Runway Approaches & Fixes
        for name, coords in CUSTOM_RUNWAY_APPROACHES:
            self.combo_box.addItem(name, coords)

        # Add top 10 busiest airports
        for label, icao in BUSIEST_AIRPORTS:
            if icao in AIRPORTS_DB:
                ap = AIRPORTS_DB[icao]
                self.combo_box.addItem(f"🔥 {label}", f"{ap['lat']},{ap['lon']}")

        # Add additional airports from database
        for icao, ap in list(AIRPORTS_DB.items())[:50]:
            if icao not in [b[1] for b in BUSIEST_AIRPORTS]:
                self.combo_box.addItem(f"{icao} - {ap['name']}", f"{ap['lat']},{ap['lon']}")

        self.combo_box.lineEdit().setPlaceholderText("Type ICAO (e.g. EGLL) or Lat,Lon")
        panel_layout.addWidget(self.combo_box)

        go_btn = QPushButton("Go To Location")
        go_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF007F;
                color: white;
                font-weight: bold;
                border: none;
                padding: 6px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #E0006F;
            }
        """)
        go_btn.clicked.connect(self.process_location_input)
        self.combo_box.lineEdit().returnPressed.connect(self.process_location_input)
        panel_layout.addWidget(go_btn)

        panel_layout.addSpacing(10)

        self.title_label = QLabel("TRACKED AIRCRAFT (CLOSEST)")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF007F;")
        panel_layout.addWidget(self.title_label)

        self.info_labels = {}
        fields = ["callsign", "airline", "actype", "registration", "origin", "destination", "distance", "hex", "alt", "speed", "heading"]
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
        self.web_page = CustomWebEnginePage(self)
        self.web_view.setPage(self.web_page)
        main_layout.addWidget(self.web_view)
        
        self.web_view.setHtml(BASE_MAP_HTML)

        self.fetch_thread = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_async_update)
        self.timer.start(5000)
        self.start_async_update()

    def process_location_input(self):
        text = self.combo_box.currentText().strip()
        data = self.combo_box.currentData()

        if data and "," in str(data):
            try:
                lat, lon = map(float, str(data).split(","))
                self.update_location(lat, lon, text)
                return
            except ValueError:
                pass

        coord_match = re.match(r"^([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)$", text)
        if coord_match:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            self.update_location(lat, lon, f"Coords: {lat:.4f}, {lon:.4f}")
            return

        icao = text.upper().strip()
        if icao in AIRPORTS_DB:
            ap = AIRPORTS_DB[icao]
            label = f"{ap['name']} ({icao})"
            self.update_location(ap["lat"], ap["lon"], label)
            return

        print("Invalid location or unknown ICAO code.")

    def update_location(self, lat, lon, label):
        self.current_lat = lat
        self.current_lon = lon
        self.selected_hex = None
        
        self.web_view.page().runJavaScript(f"setMapCenter({self.current_lat}, {self.current_lon}, '{label}');")
        self.start_async_update()

    def on_plane_selected(self, hex_code):
        clean_hex = hex_code.strip().upper()
        if clean_hex and clean_hex != self.selected_hex:
            self.selected_hex = clean_hex
        else:
            self.selected_hex = None
        
        self.start_async_update()

    def start_async_update(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            return
        self.fetch_thread = DataFetchThread(self.current_lat, self.current_lon, selected_hex=self.selected_hex)
        self.fetch_thread.data_ready.connect(self.handle_data_ready)
        self.fetch_thread.start()

    def handle_data_ready(self, data):
        aircraft_list = data.get("aircraft", [])
        tracked = data.get("tracked_plane")
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
                "dist": haversine_nm(self.current_lat, self.current_lon, lat, lon)
            })

        tracked_hex = str(tracked.get("hex", "")).upper() if tracked else ""
        closest_hex = str(closest.get("hex", "")).upper() if closest else ""

        if self.selected_hex and tracked_hex != self.selected_hex:
            self.selected_hex = None
            self.title_label.setText("TRACKED AIRCRAFT (CLOSEST)")
        elif self.selected_hex and self.selected_hex == tracked_hex:
            if self.selected_hex == closest_hex:
                self.title_label.setText("TRACKED AIRCRAFT (SELECTED & CLOSEST)")
            else:
                self.title_label.setText("TRACKED AIRCRAFT (SELECTED)")
        else:
            self.title_label.setText("TRACKED AIRCRAFT (CLOSEST)")

        self.web_view.page().runJavaScript(
            f"updateMapData({json.dumps(formatted)}, '{tracked_hex}', {json.dumps(trace)}, {self.current_lat}, {self.current_lon});"
        )

        if not tracked:
            for l in self.info_labels.values(): l.setText("--")
            return

        callsign_val = str(tracked.get("flight", "UNKNOWN")).strip()
        self.info_labels["callsign"].setText(callsign_val)
        self.info_labels["airline"].setText(get_airline_name(callsign_val))
        self.info_labels["actype"].setText(str(tracked.get("t", "N/A")))
        self.info_labels["registration"].setText(str(tracked.get("r", "N/A")))
        self.info_labels["origin"].setText(get_airport_name(route[0]))
        self.info_labels["destination"].setText(get_airport_name(route[1]))
        dist = haversine_nm(self.current_lat, self.current_lon, tracked.get("lat"), tracked.get("lon"))
        self.info_labels["distance"].setText(f"{dist:.2f} NM")
        self.info_labels["hex"].setText(tracked_hex)
        self.info_labels["alt"].setText(f"{tracked.get('alt_baro', 'N/A')} ft")
        self.info_labels["speed"].setText(f"{tracked.get('gs', 'N/A')} kts")
        self.info_labels["heading"].setText(f"{extract_heading(tracked, tracked_hex):.1f}°")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SatelliteMapTracker()
    win.show()
    sys.exit(app.exec())