import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, Crosshair } from 'lucide-react';
import { Button } from '../ui/button';

// Leaflet ships its marker icons via CSS-relative URLs that Vite doesn't
// resolve; wire them through the ESM imports so the pin actually renders.
import iconRetina from 'leaflet/dist/images/marker-icon-2x.png';
import iconStd    from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

L.Marker.prototype.options.icon = L.icon({
  iconRetinaUrl: iconRetina,
  iconUrl:       iconStd,
  shadowUrl:     iconShadow,
  iconSize:      [25, 41],
  iconAnchor:    [12, 41],
  popupAnchor:   [1, -34],
  shadowSize:    [41, 41],
});

// Internal helper — keeps the marker + map centered on the current value
// even when the parent form updates it from outside (e.g. GPS button).
function RecenterOnChange({ position }) {
  const map = useMap();
  useEffect(() => {
    if (position) map.setView(position, map.getZoom());
  }, [position, map]);
  return null;
}

// Internal helper — captures clicks anywhere on the map and forwards the
// coordinates back up to the parent form.
function ClickCapture({ onPick }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

/**
 * OfficeMapPicker — click-to-drop pin replacement for the raw lat/long
 * text inputs on the attendance settings page.
 *
 * Uses OpenStreetMap tiles (no API key, free forever). Users can either
 * click anywhere on the map OR hit "Use my current location" to snap the
 * pin to their browser GPS.
 */
export function OfficeMapPicker({ latitude, longitude, onChange }) {
  // Default view: middle of India when nothing is set yet.
  const defaultCenter = [20.5937, 78.9629];
  const hasCoords = latitude != null && longitude != null &&
                    !isNaN(latitude) && !isNaN(longitude);
  const position = hasCoords ? [Number(latitude), Number(longitude)] : null;
  const initialCenter = position || defaultCenter;
  const initialZoom = hasCoords ? 17 : 5;

  const [locating, setLocating] = useState(false);
  const mapKey = useRef(`map-${Math.random().toString(36).slice(2)}`).current;

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        onChange(pos.coords.latitude, pos.coords.longitude);
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 10000, enableHighAccuracy: true },
    );
  };

  const coordLabel = useMemo(() => {
    if (!hasCoords) return 'Click the map to drop a pin';
    return `${Number(latitude).toFixed(6)}, ${Number(longitude).toFixed(6)}`;
  }, [hasCoords, latitude, longitude]);

  return (
    <div className="space-y-2" data-testid="office-map-picker">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <MapPin className="h-4 w-4 text-green-600" />
          <span data-testid="office-map-coords">{coordLabel}</span>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleUseMyLocation}
          disabled={locating || !navigator.geolocation}
          data-testid="office-map-use-my-location"
        >
          <Crosshair className="h-3.5 w-3.5 mr-1" />
          {locating ? 'Locating…' : 'Use my current location'}
        </Button>
      </div>
      <div
        className="h-64 w-full rounded-lg overflow-hidden border border-slate-200"
        data-testid="office-map-canvas"
      >
        <MapContainer
          key={mapKey}
          center={initialCenter}
          zoom={initialZoom}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickCapture onPick={onChange} />
          {position && <Marker position={position} />}
          {position && <RecenterOnChange position={position} />}
        </MapContainer>
      </div>
    </div>
  );
}

export default OfficeMapPicker;
