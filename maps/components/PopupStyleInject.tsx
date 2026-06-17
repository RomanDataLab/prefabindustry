'use client';

import { useEffect } from 'react';

const STYLE_ID = 'mapbox-popup-no-frame';
const STYLE = `
.mapboxgl-popup.geojson-popup,
.mapboxgl-popup.csv-dot-popup{background:transparent!important;border:none!important;box-shadow:none!important}
.mapboxgl-popup.geojson-popup .mapboxgl-popup-content,
.mapboxgl-popup.csv-dot-popup .mapboxgl-popup-content{background:transparent!important;border:none!important;border-radius:0!important;padding:0!important;margin:0!important;box-shadow:none!important;min-width:0!important}
.mapboxgl-popup.geojson-popup .mapboxgl-popup-tip,
.mapboxgl-popup.csv-dot-popup .mapboxgl-popup-tip{display:none!important}
.mapboxgl-popup.geojson-popup .mapboxgl-popup-close-button,
.mapboxgl-popup.csv-dot-popup .mapboxgl-popup-close-button{display:none!important}
`;

export default function PopupStyleInject() {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement('style');
    el.id = STYLE_ID;
    el.textContent = STYLE;
    document.head.appendChild(el);
    return () => document.getElementById(STYLE_ID)?.remove();
  }, []);
  return null;
}
