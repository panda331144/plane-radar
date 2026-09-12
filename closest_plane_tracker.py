import math
import sys
import json
import requests
import airportsdata

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

AIRPORTS_DB = airportsdata.load('ICAO')

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
MY_LAT = 51.471537
MY_LON = -0.334237
RADIUS_NM = 30
DEFAULT_ZOOM = 9

HEADERS = {
    "User-Agent": "ADSBMapTracker/15.0",
    "Accept": "application/json"
}

def get_airport_name(code):
    if not code or code == "N/A":
        return "N/A"
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
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c

def fetch_route_info(callsign):
    clean_callsign = str(callsign).strip().replace(" ", "").upper() if callsign else ""
    if not clean_callsign or clean_callsign in ["UNKNOWN", "N/A", "NOCALLSIGN"]:
        return "N/A", "N/A"

    try:
        url = f"https://api.adsbdb.com/v0/callsign/{clean_callsign}"
        res = requests.get(url, headers=HEADERS, timeout=3)
        if res.status_code == 200:
            data = res.json()
            route_data = data.get("response", {}).get("flightroute", {})
            if route_data:
                orig = route_data.get("origin", {}).get("icao_code") or route_data.get("origin", {}).get("iata_code")
                dest = route_data.get("destination", {}).get("icao_code") or route_data.get("destination", {}).get("iata_code")
                if orig or dest:
                    return orig or "N/A", dest or "N/A"
    except Exception:
        pass
    return "N/A", "N/A"

def fetch_aircraft_trace(hex_code):
    """Fetches full historical trace points only for the targeted aircraft."""
    if not hex_code or hex_code == "N/A":
        return []
    
    url = f"https://opendata.adsb.fi/api/v2/trace/{hex_code.lower()}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=4)
        if res.status_code == 200:
            data = res.json()
            trace_pts = data.get("trace", [])
            
            path_coords = []
            for pt in trace_pts:
                if len(pt) >= 3 and pt[1] is not None and pt[2] is not None:
                    path_coords.append([pt[1], pt[2]])
            return path_coords
    except Exception as e:
        print(f"Trace fetch error for {hex_code}: {e}")
    return []

# Base HTML Template
BASE_MAP_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map {{
            height: 100%;
            width: 100%;
            margin: 0;
            padding: 0;
            background-color: #000000;
            overflow: hidden;
        }}

        .leaflet-div-icon {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{MY_LAT}, {MY_LON}], {DEFAULT_ZOOM});

        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 18,
            attribution: 'Tiles &copy; Esri'
        }}).addTo(map);

        L.circleMarker([{MY_LAT}, {MY_LON}], {{
            radius: 6,
            color: '#FFFFFF',
            fillColor: '#FF007F',
            fillOpacity: 1.0,
            weight: 2
        }}).bindTooltip("Monitoring Location").addTo(map);

        var aircraftMarkers = {{}};
        var highlightedTrailLine = null;
        var leadLine = null;

        function getFR24SvgPath(category) {{
            switch(category) {{
                case 'HEAVY':
                    return "M256,10 C246,10 236,32 234,70 L234,200 L30,285 C18,290 10,302 10,318 C10,332 22,340 38,332 L234,275 L234,420 L160,458 C150,463 144,473 144,484 C144,496 156,504 170,498 L256,470 L342,498 C356,504 368,496 368,484 C368,473 362,463 352,458 L278,420 L278,275 L474,332 C490,340 502,332 502,318 C502,302 494,290 482,285 L278,200 L278,70 C276,32 266,10 256,10 Z";
                case 'LIGHT':
                    return "M256,20 L242,90 L242,210 L30,230 L30,265 L242,250 L242,420 L150,450 L150,480 L256,465 L362,480 L362,450 L270,420 L270,250 L482,265 L482,230 L270,210 L270,90 Z";
                case 'TURBOPROP':
                    return "M256,15 L240,80 L240,190 L10,230 L10,265 L240,240 L240,425 L160,455 L160,485 L256,470 L352,485 L352,455 L272,425 L272,485 L502,265 L502,230 L272,190 L272,80 Z";
                case 'REGIONAL':
                    return "M256,15 C248,15 240,40 238,80 L238,220 L60,300 C50,305 45,315 45,325 C45,335 55,340 65,335 L238,285 L238,425 L180,455 L180,480 L256,465 L332,480 L332,455 L274,425 L274,285 L447,335 C457,340 467,335 467,325 C467,315 462,305 452,300 L274,220 L274,80 C272,40 264,15 256,15 Z";
                default:
                    return "M256,15 C246,15 238,35 236,75 L236,205 L40,290 C28,295 20,305 20,320 C20,332 30,340 45,332 L236,280 L236,420 L170,455 L170,482 L256,465 L342,482 L342,455 L276,420 L276,280 L467,332 C482,340 492,332 492,320 C492,305 484,295 472,290 L276,205 L276,75 C274,35 266,15 256,15 Z";
            }}
        }}

        function getAircraftCategory(actype) {{
            if (!actype || actype === 'N/A') return 'MEDIUM';
            var t = actype.toUpperCase();

            if (t.match(/^(A35[89K]|A388|B74[48]|B77[238LWW]|B78[891]|A33[2389]|A34[2356]|A306|B76[234]|C17|A124)$/)) return 'HEAVY';
            if (t.match(/^(C172|C152|C182|C208|PA28|PA34|SR20|SR22|DA40|DA42|BE36|BE58|PC12|P28A)$/)) return 'LIGHT';
            if (t.match(/^(DH8[ABCD]|AT7[25]|AT45|AT43|B350|SW4|E120|JS31)$/)) return 'TURBOPROP';
            if (t.match(/^(CRJ[1279]|E135|E145|E170|E175|E190|E195|BCS1|BCS3)$/)) return 'REGIONAL';
            return 'MEDIUM';
        }}

        function getBaseSize(category) {{
            switch(category) {{
                case 'HEAVY': return 42;
                case 'LIGHT': return 20;
                case 'TURBOPROP': return 28;
                case 'REGIONAL': return 26;
                default: return 32;
            }}
        }}

        function updateMapData(aircraftList, closestHex, closestTrace) {{
            var activeHexes = {{}};

            aircraftList.forEach(function(plane) {{
                var hex = plane.hex;
                var lat = plane.lat;
                var lon = plane.lon;
                var heading = plane.heading || 0;
                var actype = plane.actype || 'N/A';
                var isClosest = (hex === closestHex);

                activeHexes[hex] = true;

                var category = getAircraftCategory(actype);
                var baseSize = getBaseSize(category);
                var iconSize = isClosest ? Math.round(baseSize * 1.25) : baseSize;
                
                var fillHex = isClosest ? "#FF007F" : "#FFD700";
                var strokeHex = "#000000";
                var zIndex = isClosest ? 1000 : 100;

                var svgPath = getFR24SvgPath(category);
                var svgPlane = '<svg width="' + iconSize + '" height="' + iconSize + '" viewBox="0 0 512 512" style="transform: rotate(' + heading + 'deg); transform-origin: center center; filter: drop-shadow(0px 1px 3px rgba(0,0,0,0.9));">' +
                    '<path fill="' + fillHex + '" stroke="' + strokeHex + '" stroke-width="14" stroke-linejoin="round" d="' + svgPath + '"/>' +
                    '</svg>';

                var customIcon = L.divIcon({{
                    className: '',
                    html: svgPlane,
                    iconSize: [iconSize, iconSize],
                    iconAnchor: [iconSize / 2, iconSize / 2]
                }});

                var tooltipText = (isClosest ? 'TARGET [HIGHLIGHTED]: ' : '') + plane.callsign + ' [' + actype + '] (' + plane.dist.toFixed(1) + ' NM) - Heading: ' + Math.round(heading) + '°';

                // --- MARKER UPDATE ---
                if (aircraftMarkers[hex]) {{
                    aircraftMarkers[hex].setLatLng([lat, lon]);
                    aircraftMarkers[hex].setIcon(customIcon);
                    aircraftMarkers[hex].setZIndexOffset(zIndex);
                    aircraftMarkers[hex].setTooltipContent(tooltipText);
                }} else {{
                    var marker = L.marker([lat, lon], {{ icon: customIcon, zIndexOffset: zIndex }}).bindTooltip(tooltipText);
                    marker.addTo(map);
                    aircraftMarkers[hex] = marker;
                }}

                // --- HIGHLIGHTED TARGET VECTOR LINE ---
                if (isClosest) {{
                    var lineCoords = [[{MY_LAT}, {MY_LON}], [lat, lon]];
                    if (leadLine) {{
                        leadLine.setLatLngs(lineCoords);
                    }} else {{
                        leadLine = L.polyline(lineCoords, {{ color: '#FF007F', weight: 2, opacity: 0.9, dashArray: '5, 5' }}).addTo(map);
                    }}
                }}
            }});

            // --- SINGLE HIGHLIGHTED TRAIL RENDER ---
            if (closestHex && closestTrace && closestTrace.length >= 2) {{
                if (highlightedTrailLine) {{
                    highlightedTrailLine.setLatLngs(closestTrace);
                }} else {{
                    highlightedTrailLine = L.polyline(closestTrace, {{
                        color: '#FF007F',
                        weight: 3.5,
                        opacity: 0.9,
                        lineCap: 'round',
                        lineJoin: 'round'
                    }}).addTo(map);
                }}
            }} else {{
                if (highlightedTrailLine) {{
                    map.removeLayer(highlightedTrailLine);
                    highlightedTrailLine = null;
                }}
            }}

            // Clean up left-range aircraft
            for (var hex in aircraftMarkers) {{
                if (!activeHexes[hex]) {{
                    map.removeLayer(aircraftMarkers[hex]);
                    delete aircraftMarkers[hex];
                }}
            }}

            if (!closestHex && leadLine) {{
                map.removeLayer(leadLine);
                leadLine = null;
            }}
        }}
    </script>
</body>
</html>
"""


class SatelliteMapTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Satellite ADSB Aircraft Tracker - FR24 Style")
        self.setGeometry(100, 100, 1200, 750)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Telemetry Panel
        self.data_panel = QWidget()
        self.data_panel.setFixedWidth(320)
        self.data_panel.setStyleSheet("background-color: #121212; color: #FFFFFF; font-family: Segoe UI, Arial;")
        
        panel_layout = QVBoxLayout(self.data_panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("TRACKED AIRCRAFT")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FF007F; margin-bottom: 10px;")
        panel_layout.addWidget(title)

        self.info_labels = {}
        fields = [
            ("Flight / Callsign", "callsign"),
            ("Aircraft Type", "actype"),
            ("Tail / Registration", "registration"),
            ("Origin Airport", "origin"),
            ("Destination Airport", "destination"),
            ("Distance", "distance"),
            ("ICAO Hex", "hex"),
            ("Squawk Code", "squawk"),
            ("Altitude", "alt"),
            ("Ground Speed", "speed"),
            ("Heading", "heading"),
            ("Vertical Speed", "vspeed"),
            ("Latitude", "lat"),
            ("Longitude", "lon")
        ]

        for label_text, key in fields:
            lbl_title = QLabel(label_text.upper())
            lbl_title.setStyleSheet("font-size: 10px; color: #888888; font-weight: bold; margin-top: 4px;")
            lbl_val = QLabel("--")
            lbl_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFF;")
            lbl_val.setWordWrap(True)
            
            panel_layout.addWidget(lbl_title)
            panel_layout.addWidget(lbl_val)
            self.info_labels[key] = lbl_val

        panel_layout.addStretch()
        main_layout.addWidget(self.data_panel)

        # Web View Setup
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #000000;")

        main_layout.addWidget(self.web_view)

        # Load Base HTML
        self.web_view.setHtml(BASE_MAP_HTML, QUrl("https://localhost"))

        # 5-second polling loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_tracker)
        self.timer.start(5000)

        self.update_tracker()

    def get_aircraft(self):
        url = f"https://opendata.adsb.fi/api/v2/lat/{MY_LAT}/lon/{MY_LON}/dist/{RADIUS_NM}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=5)
            if res.status_code == 200:
                data = res.json()
                return data.get("ac", data.get("aircraft", []))
        except Exception as e:
            print(f"Fetch error: {e}")
        return []

    def clear_panel(self):
        for key, lbl in self.info_labels.items():
            if key == "callsign":
                lbl.setText("NO TARGET")
                lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF5252;")
            else:
                lbl.setText("--")

    def update_tracker(self):
        aircraft_list = self.get_aircraft()
        closest_plane = None
        min_dist = float("inf")

        formatted_aircraft = []

        for plane in aircraft_list:
            p_lat = plane.get("lat")
            p_lon = plane.get("lon")
            if p_lat is None or p_lon is None:
                continue
            
            p_hex = str(plane.get("hex", "N/A")).upper()
            callsign = str(plane.get("flight", "N/A")).strip()
            actype = plane.get("t", "N/A")
            heading = float(plane.get("track", 0) or 0)
            dist = haversine_nm(MY_LAT, MY_LON, p_lat, p_lon)

            formatted_aircraft.append({
                "hex": p_hex,
                "lat": p_lat,
                "lon": p_lon,
                "callsign": callsign,
                "actype": actype,
                "heading": heading,
                "dist": dist
            })

            if dist < min_dist:
                min_dist = dist
                closest_plane = plane

        closest_hex = str(closest_plane.get("hex", "")).upper() if closest_plane else ""
        closest_trace = []

        # Only fetch and pass historical trace for the single closest target
        if closest_plane:
            p_lat = closest_plane.get("lat")
            p_lon = closest_plane.get("lon")
            closest_trace = fetch_aircraft_trace(closest_hex)
            if not closest_trace or closest_trace[-1] != [p_lat, p_lon]:
                closest_trace.append([p_lat, p_lon])

        # Execute map update with single target trace
        js_payload = json.dumps(formatted_aircraft)
        js_trace_payload = json.dumps(closest_trace)
        self.web_view.page().runJavaScript(f"updateMapData({js_payload}, '{closest_hex}', {js_trace_payload});")

        if not closest_plane:
            self.clear_panel()
            return

        callsign = str(closest_plane.get("flight", "UNKNOWN")).strip()
        actype = closest_plane.get("t", "N/A")
        registration = closest_plane.get("r", "N/A")
        hex_code = str(closest_plane.get("hex", "N/A")).upper()

        origin = closest_plane.get("orig_icao") or closest_plane.get("origin")
        destination = closest_plane.get("dest_icao") or closest_plane.get("destination")

        if not origin or not destination or origin == "N/A" or destination == "N/A":
            fetched_orig, fetched_dest = fetch_route_info(callsign)
            origin = origin if origin and origin != "N/A" else fetched_orig
            destination = destination if destination and destination != "N/A" else fetched_dest

        squawk = closest_plane.get("squawk", "N/A")
        alt = closest_plane.get("alt_baro", closest_plane.get("alt_geom", "N/A"))
        speed = closest_plane.get("gs", "N/A")
        heading = closest_plane.get("track", "N/A")
        vspeed = closest_plane.get("baro_rate", closest_plane.get("geom_rate", 0))

        self.info_labels["callsign"].setText(callsign if callsign else "NO CALLSIGN")
        self.info_labels["callsign"].setStyleSheet("font-size: 16px; font-weight: bold; color: #FF007F;")
        self.info_labels["actype"].setText(str(actype) if actype else "UNSPECIFIED")
        self.info_labels["registration"].setText(str(registration) if registration else "N/A")
        self.info_labels["origin"].setText(get_airport_name(origin))
        self.info_labels["destination"].setText(get_airport_name(destination))
        self.info_labels["distance"].setText(f"{min_dist:.2f} NM")
        self.info_labels["hex"].setText(hex_code)
        self.info_labels["squawk"].setText(str(squawk))
        self.info_labels["alt"].setText(f"{alt} ft" if alt != "N/A" else "N/A")
        self.info_labels["speed"].setText(f"{speed} kts" if speed != "N/A" else "N/A")
        self.info_labels["heading"].setText(f"{heading}°" if heading != "N/A" else "N/A")
        self.info_labels["vspeed"].setText(f"{vspeed} fpm")
        self.info_labels["lat"].setText(f"{closest_plane.get('lat'):.4f}")
        self.info_labels["lon"].setText(f"{closest_plane.get('lon'):.4f}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SatelliteMapTracker()
    win.show()
    sys.exit(app.exec())