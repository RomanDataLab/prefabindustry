'use client';

import { useEffect, useRef } from 'react';
import Head from 'next/head';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

interface MapboxConfig {
  MAPBOX_ACCESS_TOKEN: string;
  MAPBOX_STYLE: string;
}

export default function MapDots() {
    const mapContainer = useRef<HTMLDivElement>(null);
    const map = useRef<mapboxgl.Map | null>(null);
    const markersRef = useRef<mapboxgl.Marker[]>([]);

    useEffect(() => {
        if (!mapContainer.current || map.current) return;

        let isMounted = true;

        // Load Mapbox config
        fetch('/api/mapbox-config')
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }
                return res.json();
            })
            .then((data: MapboxConfig) => {
                if (!isMounted) return;
                
                mapboxgl.accessToken = data.MAPBOX_ACCESS_TOKEN || '';
                
                if (!mapContainer.current) return;
                
                map.current = new mapboxgl.Map({
                    container: mapContainer.current,
                    style: data.MAPBOX_STYLE || 'mapbox://styles/mapbox/dark-v11',
                    center: [10.4515, 51.1657],
                    zoom: 4
                });

                map.current.on('load', () => {
                    if (!isMounted) return;
                    loadCSVAndAddDots();
                });

                map.current.on('error', (e) => {
                    console.error('Mapbox error:', e);
                });
            })
            .catch((err: Error) => {
                console.error('Error loading config:', err);
                if (!isMounted || !mapContainer.current) return;
                
                mapboxgl.accessToken = '';
                map.current = new mapboxgl.Map({
                    container: mapContainer.current,
                    style: 'mapbox://styles/mapbox/dark-v11',
                    center: [10.4515, 51.1657],
                    zoom: 4
                });
                map.current.on('load', () => {
                    if (isMounted) {
                        loadCSVAndAddDots();
                    }
                });
            });

        return () => {
            isMounted = false;
            markersRef.current.forEach(marker => {
                try {
                    marker.remove();
                } catch (e) {
                    // Ignore errors during cleanup
                }
            });
            if (map.current) {
                try {
                    map.current.remove();
                } catch (e) {
                    // Ignore errors during cleanup
                }
                map.current = null;
            }
        };
    }, []);

    const loadCSVAndAddDots = (): void => {
        if (!map.current || !map.current.loaded()) {
            console.log('Map not ready for CSV dots, waiting...');
            setTimeout(() => loadCSVAndAddDots(), 100);
            return;
        }

        // Parse CSV line handling quoted values
        const parseCSVLine = (line: string): string[] => {
            const result: string[] = [];
            let current = '';
            let inQuotes = false;

            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                
                if (char === '"') {
                    inQuotes = !inQuotes;
                } else if (char === ',' && !inQuotes) {
                    result.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
            result.push(current.trim());
            return result;
        };

        // Remove existing markers
        markersRef.current.forEach((marker) => marker.remove());
        markersRef.current = [];

        // Load prefab company locations from public/prefabworldfin_reducedby_7.csv
        fetch('/prefabworldfin_reducedby_7.csv')
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.text();
            })
            .then((csvText: string) => {
                if (!csvText || !map.current) return;

                const lines = csvText.split('\n').filter((l) => l.trim());
                
                if (lines.length === 0) {
                    console.error('CSV is empty');
                    return;
                }

                // Parse CSV header and find explicit latitude/longitude columns from prefabworldfin_reducedby_7.csv
                const headers = parseCSVLine(lines[0]);
                const latColIndex = headers.indexOf('latitude');
                const lonColIndex = headers.indexOf('longitude');
                if (latColIndex === -1 || lonColIndex === -1) {
                    console.error('Could not find latitude/longitude columns in CSV header', headers);
                    return;
                }

                let validDots = 0;

                // Process each row (skip header)
                for (let i = 1; i < lines.length; i++) {
                    const values = parseCSVLine(lines[i]);
                    
                    if (values.length < headers.length) {
                        continue; // Skip incomplete rows
                    }

                    const latStr = values[latColIndex];
                    const lonStr = values[lonColIndex];
                    
                    const lat = parseFloat(latStr);
                    const lon = parseFloat(lonStr);

                    // Validate coordinates
                    if (isNaN(lat) || isNaN(lon)) {
                        continue;
                    }

                    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                        continue;
                    }

                    // Create red circle element - 5px diameter
                    const el = document.createElement('div');
                    el.style.width = '5px';
                    el.style.height = '5px';
                    el.style.borderRadius = '50%';
                    el.style.backgroundColor = '#ff0000';
                    el.style.cursor = 'pointer';
                    el.style.display = 'block';
                    el.style.pointerEvents = 'auto';

                    // Create marker
                    const marker = new mapboxgl.Marker({ 
                        element: el,
                        anchor: 'center'
                    })
                        .setLngLat([lon, lat])
                        .addTo(map.current!);

                    markersRef.current.push(marker);
                    validDots++;
                }

                console.log(`Added ${validDots} red dots (5px) to map`);

                // Fit map to bounds if we have markers
                if (validDots > 0 && map.current) {
                    const bounds = new mapboxgl.LngLatBounds();
                    markersRef.current.forEach((marker) => {
                        const lngLat = marker.getLngLat();
                        bounds.extend([lngLat.lng, lngLat.lat]);
                    });
                    
                    if (bounds.getNorth() !== bounds.getSouth() || bounds.getEast() !== bounds.getWest()) {
                        map.current.fitBounds(bounds, { padding: 50 });
                    }
                }
            })
            .catch((error: Error) => {
                console.error('Error loading CSV:', error);
            });
    };

    return (
        <>
            <Head>
                <title>Map Dots - Prefab World</title>
                <meta name="viewport" content="width=device-width, initial-scale=1" />
            </Head>
            <div style={{ width: '100%', height: '100vh', position: 'relative' }}>
                <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
            </div>
        </>
    );
}
