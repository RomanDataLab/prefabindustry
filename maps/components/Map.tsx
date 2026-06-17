'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import mapboxgl from 'mapbox-gl';

const useIsMobile = (breakpoint = 768) => {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${breakpoint}px)`);
    setIsMobile(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [breakpoint]);
  return isMobile;
};
// Simple house icon SVG path (house with chimney window)
const HOUSE_ICON_SVG = `<svg viewBox="0 0 576 512" style="width: 20px; height: 20px; fill: #ff0000;">
  <path d="M575.8 255.5c0 18-15 32.1-32 32.1h-32l.7 160.2c0 2.7-.2 5.4-.5 8.1V472c0 22.1-17.9 40-40 40H456c-1.1 0-2.2 0-3.3-.1c-1.4 .1-2.8 .1-4.2 .1H416 392c-22.1 0-40-17.9-40-40V448 384c0-17.7-14.3-32-32-32H256c-17.7 0-32 14.3-32 32v64 24c0 22.1-17.9 40-40 40H160 128.1c-1.5 0-3-.1-4.5-.2c-1.2 .1-2.4 .2-3.6 .2H104c-22.1 0-40-17.9-40-40V360c0-.9 0-1.9 .1-2.8l-.1-1.8V256H32c-17 0-32-14-32-32.1c0-9 3-17 10-24L266.4 8c7-7 15-8 22-8s15 2 21 7L564.8 231.5c8 7 12 15 11 24z"/>
</svg>`;
const PANELS_ICON_URL = 'https://cdn-icons-png.flaticon.com/512/3405/3405248.png';

interface MapboxConfig {
  MAPBOX_ACCESS_TOKEN: string;
  MAPBOX_STYLE: string;
}

interface DashboardCompany {
  id: string;
  brand: string;
  webpage: string;
  latitude: number;
  longitude: number;
  country: string;
  countryCode: string;
  region: string;
  address: string;
  type: string;
  mainStructureMaterial: string;
  modelsAmount: number | null;
  minSqm: number | null;
  medianSqm: number | null;
  maxSqm: number | null;
  minHomePriceK: number | null;
  medianUPriceK: number | null;
  configurator: string;
  desc: string;
  vizUrls: string[];
  planUrls: string[];
  flagUrl: string;
  iconColor: string;
}

interface DashboardPayload {
  count: number;
  companies: DashboardCompany[];
}

const useDashboardCompanies = () =>
  useQuery<DashboardCompany[]>({
    queryKey: ['prefab-dashboard-data'],
    queryFn: async () => {
      const response = await fetch('/prefab-dashboard-data.json');
      if (!response.ok) throw new Error(`Failed to load dashboard data (${response.status})`);
      const payload = (await response.json()) as DashboardPayload;
      return payload.companies || [];
    },
  });

const formatNum = (v: number | null): string => {
  if (v === null || Number.isNaN(v)) return '—';
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
};

export default function Map() {
  const isMobile = useIsMobile();
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const popup = useRef<mapboxgl.Popup | null>(null);
  const layersLoaded = useRef<boolean>(false);
  const csvMarkersRef = useRef<mapboxgl.Marker[]>([]);
  const markerDataRef = useRef<
    Array<{ marker: mapboxgl.Marker; originalLng: number; originalLat: number; legendKey: string }>
  >([]);
  const [config, setConfig] = useState<MapboxConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [legendCounts, setLegendCounts] = useState<Record<string, number>>({});
  const [selectedCompany, setSelectedCompany] = useState<DashboardCompany | null>(null);
  const companyIndexRef = useRef<Record<string, DashboardCompany>>({});
  const [hiddenCategories, setHiddenCategories] = useState<Set<string>>(new Set());
  const [visibleIsoIds, setVisibleIsoIds] = useState<Set<string>>(new Set());
  const isoAvailableRef = useRef<Set<string>>(new Set());
  const [isoLoaded, setIsoLoaded] = useState(false);
  const [legendCollapsed, setLegendCollapsed] = useState(false);
  const [dashpanelHidden, setDashpanelHidden] = useState(false);
  const isoLoadingRef = useRef(false);

  // Auto-collapse legend on mobile, auto-hide dashpanel
  const initialMobileRef = useRef(false);
  useEffect(() => {
    if (isMobile && !initialMobileRef.current) {
      initialMobileRef.current = true;
      setLegendCollapsed(true);
      setDashpanelHidden(true);
    }
  }, [isMobile]);

  const ISO_SOURCE = 'iso-all';
  const ISO_FILL = 'iso-fill';

  const { data: dashboardCompanies } = useDashboardCompanies();

  // Build a lookup by id once companies load
  useEffect(() => {
    if (!dashboardCompanies?.length) return;
    const idx: Record<string, DashboardCompany> = {};
    for (const c of dashboardCompanies) idx[c.id] = c;
    companyIndexRef.current = idx;
  }, [dashboardCompanies]);

  // Update isochrone filter when visibleIsoIds changes
  const buildIsoFilter = (ids: Set<string>): any => {
    if (ids.size === 0) return ['==', ['get', 'company_id'], '__none__'];
    return ['in', ['get', 'company_id'], ['literal', Array.from(ids)]];
  };

  useEffect(() => {
    const m = map.current;
    if (!m || !m.getLayer(ISO_FILL)) return;
    try { m.setFilter(ISO_FILL, buildIsoFilter(visibleIsoIds)); } catch {}
  }, [visibleIsoIds]);

  // Show isochrones when a company is selected (accumulate, never remove)
  useEffect(() => {
    if (!selectedCompany) return;
    if (!isoAvailableRef.current.has(selectedCompany.id)) return;
    setVisibleIsoIds((old) => {
      if (old.has(selectedCompany.id)) return old;
      const next = new Set(old);
      next.add(selectedCompany.id);
      return next;
    });
  }, [selectedCompany]);

  // Zurich center coordinates: 47.3769° N, 8.5417° E
  const ZURICH_LAT = 47.3769;
  const ZURICH_LNG = 8.5417;
  const DEFAULT_ZOOM = 6;

  useEffect(() => {
    // Fetch Mapbox config from API
    fetch('/api/mapbox-config')
      .then(res => {
        if (!res.ok) {
          return res.json().then(err => {
            throw new Error(err.error || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data: MapboxConfig) => {
        console.log('Mapbox config loaded:', { 
          hasToken: !!data.MAPBOX_ACCESS_TOKEN, 
          style: data.MAPBOX_STYLE 
        });
        if (data.MAPBOX_ACCESS_TOKEN) {
          setConfig(data);
        } else {
          setError('Mapbox access token not found in config');
        }
      })
      .catch(err => {
        console.error('Error loading Mapbox config:', err);
        setError(`Failed to load Mapbox configuration: ${err.message}`);
      });
  }, []);

  useEffect(() => {
    if (!config || !mapContainer.current || map.current) return;

    // Set Mapbox access token
    mapboxgl.accessToken = config.MAPBOX_ACCESS_TOKEN;

    const mapStyle = 'mapbox://styles/mapbox/dark-v11';

    try {
      // Initialize map with flat projection (not globe)
      map.current = new mapboxgl.Map({
        container: mapContainer.current,
        style: mapStyle,
        center: [ZURICH_LNG, ZURICH_LAT],
        zoom: DEFAULT_ZOOM,
        projection: 'mercator', // Flat projection instead of globe
      });

      // Configure scroll zoom to zoom around screen center
      const container = mapContainer.current;
      if (container) {
        // Set up wheel handler immediately
        map.current.once('load', () => {
          // Disable default scroll zoom after map loads
          if (map.current) {
            map.current.scrollZoom.disable();
          }
        });
        
        const wheelHandler = (e: WheelEvent) => {
          if (!map.current) return;
          
          // Get container dimensions
          const width = container.clientWidth || container.offsetWidth;
          const height = container.clientHeight || container.offsetHeight;
          
          // Validate dimensions
          if (!width || !height || width === 0 || height === 0) return;
          
          // Get center point of the screen
          const centerX = width / 2;
          const centerY = height / 2;
          
          // Validate center point
          if (isNaN(centerX) || isNaN(centerY)) return;
          
          const centerPoint = new mapboxgl.Point(centerX, centerY);
          const centerLngLat = map.current.unproject(centerPoint);

          // Validate unprojected coordinates
          if (!centerLngLat || isNaN(centerLngLat.lng) || isNaN(centerLngLat.lat)) return;

          // Get current zoom
          const currentZoom = map.current.getZoom();
          if (isNaN(currentZoom)) return;

          // Calculate zoom delta
          const zoomSpeed = 0.0015;
          const zoomDelta = -e.deltaY * zoomSpeed;
          const newZoom = Math.max(0, Math.min(22, currentZoom + zoomDelta));

          // Prevent default to stop Mapbox's default zoom
          e.preventDefault();
          e.stopPropagation();

          // Zoom around center LngLat
          try {
            map.current.zoomTo(newZoom, {
              around: centerLngLat,
              duration: 0
            } as mapboxgl.AnimationOptions & { around?: mapboxgl.LngLat });
          } catch (err) {
            console.error('Zoom error:', err);
          }
        };
        
        // Add event listener immediately with capture phase
        container.addEventListener('wheel', wheelHandler, { passive: false, capture: true });
        
        // Store handler for cleanup
        (map.current as any)._customWheelHandler = wheelHandler;
      }

      // Handle map load errors
      map.current.on('error', (e) => {
        console.error('Mapbox error:', e);
        setError(`Map error: ${e.error?.message || 'Unknown error'}`);
      });

      // Initialize popup for GeoJSON regions
      popup.current = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        className: 'geojson-popup',
      });

      // Handle map load - add GeoJSON layer, CSV dots, and isochrones
      map.current.once('load', () => {
        console.log('Map loaded successfully');
        if (!layersLoaded.current) {
          layersLoaded.current = true;
          loadGeoJSONLayer();
          loadCSVAndAddDots();
        }
      });

      // Update marker positions on zoom/move to avoid overlaps
      const updateMarkerPositions = () => {
        if (!map.current || markerDataRef.current.length === 0) return;
        
        const zoom = map.current.getZoom();
        const iconSize = 20; // Icon size in pixels
        const minDistance = iconSize + 2; // Minimum distance between icons
        
        // Calculate spacing factor based on zoom level
        // Higher zoom = less spacing (icons move closer to original position)
        // At zoom 3: spacingFactor = 0, full separation
        // At zoom 13+: spacingFactor = 1, no separation (exact positions)
        const spacingFactor = Math.max(0, Math.min(1, (zoom - 3) / 10));
        
        // Convert all original positions to screen coordinates
        const screenPositions = markerDataRef.current.map(data => {
          const point = map.current!.project([data.originalLng, data.originalLat]);
          return { x: point.x, y: point.y, data };
        });
        
        // Adjust positions to avoid overlaps
        screenPositions.forEach((pos, i) => {
          let adjustedX = pos.x;
          let adjustedY = pos.y;
          
          // Check collisions with all previous markers
          for (let j = 0; j < i; j++) {
            const otherPos = screenPositions[j];
            const dx = adjustedX - otherPos.x;
            const dy = adjustedY - otherPos.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            if (distance < minDistance && distance > 0) {
              // Calculate separation vector
              const angle = Math.atan2(dy, dx);
              const separation = (minDistance - distance) * (1 - spacingFactor) * 0.5;
              
              adjustedX += Math.cos(angle) * separation;
              adjustedY += Math.sin(angle) * separation;
              
              // Also push the other marker away slightly
              screenPositions[j].x -= Math.cos(angle) * separation;
              screenPositions[j].y -= Math.sin(angle) * separation;
            }
          }
          
          pos.x = adjustedX;
          pos.y = adjustedY;
        });
        
        // Update marker positions
        screenPositions.forEach((pos) => {
          const adjustedLngLat = map.current!.unproject([pos.x, pos.y]);
          
          // Interpolate between original and adjusted position based on zoom
          const finalLng = pos.data.originalLng * spacingFactor + adjustedLngLat.lng * (1 - spacingFactor);
          const finalLat = pos.data.originalLat * spacingFactor + adjustedLngLat.lat * (1 - spacingFactor);
          
          pos.data.marker.setLngLat([finalLng, finalLat]);
        });
      };

      // Update positions on zoom and move (throttled)
      let updateTimeout: NodeJS.Timeout | null = null;
      const throttledUpdate = () => {
        if (updateTimeout) return;
        updateTimeout = setTimeout(() => {
          updateMarkerPositions();
          updateTimeout = null;
        }, 50); // Throttle to every 50ms
      };

      map.current.on('zoom', throttledUpdate);
      map.current.on('move', throttledUpdate);
      map.current.on('zoomend', updateMarkerPositions);
      map.current.on('moveend', updateMarkerPositions);

      // Zoom controls are rendered in the custom floating legend panel.
    } catch (err) {
      console.error('Error initializing map:', err);
      setError(`Failed to initialize map: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }

    return () => {
      layersLoaded.current = false;
      csvMarkersRef.current.forEach(marker => {
        try {
          marker.remove();
        } catch (e) {
          // Ignore errors during cleanup
        }
      });
      csvMarkersRef.current = [];
      markerDataRef.current = [];
      if (popup.current) {
        popup.current.remove();
        popup.current = null;
      }
      if (map.current) {
        // Remove custom wheel handler if it exists
        const container = mapContainer.current;
        if (container && (map.current as any)._customWheelHandler) {
          container.removeEventListener('wheel', (map.current as any)._customWheelHandler);
        }
        map.current.remove();
        map.current = null;
      }
    };
  }, [config]);

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

    // Remove existing CSV markers
    csvMarkersRef.current.forEach((marker) => marker.remove());
    csvMarkersRef.current = [];

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
        if (lines.length === 0) return;

        const headers = parseCSVLine(lines[0]);

        // Find latitude/longitude columns by header name in prefabworldfin_reducedby_7.csv
        const latColIndex = headers.indexOf('latitude');
        const lonColIndex = headers.indexOf('longitude');
        if (latColIndex === -1 || lonColIndex === -1) {
          console.error('Could not find latitude/longitude columns in CSV header', headers);
          return;
        }
        const idColIndex = headers.indexOf('id');
        const brandColIndex = headers.indexOf('brand');
        const webpageColIndex = headers.indexOf('webpage');
        const materialColIndex = headers.indexOf('main_structure_material');
        const typeColIndex = headers.indexOf('type');

        const getLegendKey = (material: string, itemType: string): string => {
          if (itemType && itemType.trim().toLowerCase() === 'panels') return 'panels';
          if (!material || material.trim() === '' || material === 'NaN') return 'unknown';
          const m = material.trim().toLowerCase();
          switch (m) {
            case 'hempcrete':
              return 'hempcrete';
            case 'bamboo':
              return 'hempcrete';
            case 'wood':
            case 'wood/timber':
              return 'wood';
            case 'clt':
              return 'clt';
            case 'composite':
            case 'sip':
              return 'composite';
            case 'concrete':
              return 'concrete';
            case 'aac blocks':
              return 'aac_blocks';
            case 'steel':
              return 'steel';
            default:
              return 'unknown';
          }
        };

        // Color mapping by legend key
        const getMaterialColor = (legendKey: string): string => {
          switch (legendKey) {
            case 'hempcrete':
              return '#00bfa5'; // Inherit bamboo color
            case 'wood':
              return '#006400'; // Dark green
            case 'clt':
              return '#ffd700'; // Yellow
            case 'composite':
              return '#ff8c00'; // Orange
            case 'concrete':
              return '#ff0000'; // Red
            case 'aac_blocks':
              return '#8a2be2'; // Violet
            case 'steel':
              return '#1e90ff'; // Blue
            default:
              return '#888888'; // Gray for unknown
          }
        };

        let validDots = 0;
        const counts: Record<string, number> = {};

        // Process each row (skip header)
        for (let i = 1; i < lines.length; i++) {
          const values = parseCSVLine(lines[i]);
          
          if (values.length < headers.length) continue;

          const rowId = idColIndex >= 0 ? values[idColIndex].trim() : '';
          const latStr = values[latColIndex];
          const lonStr = values[lonColIndex];
          const brand = brandColIndex >= 0 ? values[brandColIndex] : '';
          const webpage = webpageColIndex >= 0 ? values[webpageColIndex] : '';
          const material = materialColIndex >= 0 ? values[materialColIndex] : '';
          const itemType = typeColIndex >= 0 ? values[typeColIndex] : '';
          
          const lat = parseFloat(latStr);
          const lon = parseFloat(lonStr);

          // Validate coordinates
          if (isNaN(lat) || isNaN(lon)) continue;
          if (lat < -90 || lat > 90 || lon < -180 || lon > 180) continue;

          const legendKey = getLegendKey(material, itemType);
          counts[legendKey] = (counts[legendKey] || 0) + 1;

          // Get color based on material category
          const iconColor = getMaterialColor(legendKey);

          // Create home icon element with material-based color
          const el = document.createElement('div');
          // Use special icon for panels; otherwise use material-colored house icon
          if (itemType && itemType.trim().toLowerCase() === 'panels') {
            const img = document.createElement('img');
            img.src = PANELS_ICON_URL;
            img.alt = 'Panels icon';
            img.width = 20;
            img.height = 20;
            img.style.display = 'block';
            img.style.width = '20px';
            img.style.height = '20px';
            img.style.filter = 'brightness(0) invert(1)';
            img.style.opacity = '1';
            el.appendChild(img);
          } else {
            const coloredSvg = HOUSE_ICON_SVG.replace('fill: #ff0000', `fill: ${iconColor}`);
            el.innerHTML = coloredSvg;
          }
          el.style.cursor = 'pointer';
          el.style.display = 'flex';
          el.style.alignItems = 'center';
          el.style.justifyContent = 'center';
          el.style.pointerEvents = 'auto';
          el.style.width = '20px';
          el.style.height = '20px';

          // Create marker
          const marker = new mapboxgl.Marker({ 
            element: el,
            anchor: 'center'
          })
            .setLngLat([lon, lat])
            .addTo(map.current!);

          // Add click handler to show popup and select company in dashboard
          el.addEventListener('click', (e: MouseEvent) => {
            e.stopPropagation();

            // Close any existing CSV popups
            document.querySelectorAll('.csv-dot-popup').forEach((popup) => {
              popup.remove();
            });

            // Create popup content with red bold brand text as link
            const popupContent = webpage && webpage.trim()
              ? `<a href="${webpage}" target="_blank" rel="noopener noreferrer">${brand || 'Unknown'}</a>`
              : `<span>${brand || 'Unknown'}</span>`;

            // Create popup with no background/frame
            const popup = new mapboxgl.Popup({
              closeButton: false,
              closeOnClick: true,
              anchor: 'bottom',
              offset: 5,
              className: 'csv-dot-popup'
            })
              .setLngLat([lon, lat])
              .setHTML(popupContent)
              .addTo(map.current!);

            // Select company in dashboard panel
            if (rowId) {
              const company = companyIndexRef.current[rowId];
              if (company) setSelectedCompany(company);
            }
          });

          csvMarkersRef.current.push(marker);
          markerDataRef.current.push({
            marker,
            originalLng: lon,
            originalLat: lat,
            legendKey,
          });
          validDots++;
        }

        setLegendCounts(counts);
        console.log(`Added ${validDots} red home icons from CSV`);
        
        // Update marker positions to avoid overlaps
        if (map.current) {
          setTimeout(() => {
            const updateMarkerPositions = () => {
              if (!map.current || markerDataRef.current.length === 0) return;
              
              const zoom = map.current.getZoom();
              const iconSize = 20;
              const minDistance = iconSize + 2;
              const spacingFactor = Math.max(0, Math.min(1, (zoom - 3) / 10));
              
              const screenPositions = markerDataRef.current.map(data => {
                const point = map.current!.project([data.originalLng, data.originalLat]);
                return { x: point.x, y: point.y, data };
              });
              
              screenPositions.forEach((pos, i) => {
                let adjustedX = pos.x;
                let adjustedY = pos.y;
                
                for (let j = 0; j < i; j++) {
                  const otherPos = screenPositions[j];
                  const dx = adjustedX - otherPos.x;
                  const dy = adjustedY - otherPos.y;
                  const distance = Math.sqrt(dx * dx + dy * dy);
                  
                  if (distance < minDistance && distance > 0) {
                    const angle = Math.atan2(dy, dx);
                    const separation = (minDistance - distance) * (1 - spacingFactor) * 0.5;
                    adjustedX += Math.cos(angle) * separation;
                    adjustedY += Math.sin(angle) * separation;
                    screenPositions[j].x -= Math.cos(angle) * separation;
                    screenPositions[j].y -= Math.sin(angle) * separation;
                  }
                }
                
                pos.x = adjustedX;
                pos.y = adjustedY;
              });
              
              screenPositions.forEach((pos) => {
                const adjustedLngLat = map.current!.unproject([pos.x, pos.y]);
                const finalLng = pos.data.originalLng * spacingFactor + adjustedLngLat.lng * (1 - spacingFactor);
                const finalLat = pos.data.originalLat * spacingFactor + adjustedLngLat.lat * (1 - spacingFactor);
                pos.data.marker.setLngLat([finalLng, finalLat]);
              });
            };
            updateMarkerPositions();
          }, 100);
        }
      })
      .catch((error: Error) => {
        console.error('Error loading CSV:', error);
      });
  };

  const loadGeoJSONLayer = (): void => {
    // GeoJSON overlay loading removed by request.
  };


  if (error) {
    return (
      <div style={{ 
        width: '100%', 
        height: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        backgroundColor: '#000',
        color: '#fff'
      }}>
        <div>Error: {error}</div>
      </div>
    );
  }

  if (!config) {
    return (
      <div
        style={{
          width: '100%',
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#000',
          color: '#fff',
        }}
      >
        <div>Loading map...</div>
      </div>
    );
  }

  const LEGEND_ITEMS: Array<{ key: string; label: string; color?: string; panels?: boolean }> = [
    { key: 'panels', label: 'panels', panels: true },
    { key: 'hempcrete', label: 'hempcrete', color: '#00bfa5' },
    { key: 'wood', label: 'wood', color: '#006400' },
    { key: 'clt', label: 'CLT', color: '#ffd700' },
    { key: 'composite', label: 'composite', color: '#ff8c00' },
    { key: 'concrete', label: 'concrete', color: '#ff0000' },
    { key: 'steel', label: 'steel', color: '#1e90ff' },
    { key: 'unknown', label: 'unknown', color: '#888888' },
  ];

  const toggleCategory = (key: string) => {
    setHiddenCategories((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      // Show/hide markers immediately
      for (const md of markerDataRef.current) {
        if (md.legendKey === key) {
          md.marker.getElement().style.display = next.has(key) ? 'none' : '';
        }
      }
      return next;
    });
  };

  const zoomBy = (delta: number): void => {
    if (!map.current) return;
    const currentZoom = map.current.getZoom();
    const nextZoom = Math.max(0, Math.min(22, currentZoom + delta));
    map.current.easeTo({ zoom: nextZoom, duration: 120 });
  };

  const loadIsochrones = () => {
    if (isoLoaded || isoLoadingRef.current || !map.current) return;
    isoLoadingRef.current = true;
    fetch('/isochrones_all.geojson')
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (!geo?.features?.length || !map.current) return;
        const ids = new Set<string>();
        for (const f of geo.features) {
          const cid = String(f?.properties?.company_id || '').trim();
          if (cid) ids.add(cid);
        }
        isoAvailableRef.current = ids;
        console.log(`Loaded isochrones for ${ids.size} companies`);
        map.current.addSource(ISO_SOURCE, { type: 'geojson', data: geo });
        const layers = map.current.getStyle()?.layers || [];
        const firstSymbol = layers.find((l) => l.type === 'symbol')?.id;
        const emptyFilter: any = ['==', ['get', 'company_id'], '__none__'];
        map.current.addLayer(
          {
            id: ISO_FILL,
            type: 'fill',
            source: ISO_SOURCE,
            filter: emptyFilter,
            paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.2 },
          },
          firstSymbol,
        );
        setIsoLoaded(true);
      })
      .catch(() => {})
      .finally(() => { isoLoadingRef.current = false; });
  };


  return (
    <div
      style={{
        width: '100%',
        height: '100vh',
        position: 'relative',
      }}
    >
      <div
        ref={mapContainer}
        style={{
          width: '100%',
          height: '100vh',
          backgroundColor: '#000000',
        }}
      />
      <div
        className="legend-panel"
        style={{
          position: 'absolute',
          top: isMobile ? 'auto' : 12,
          bottom: isMobile ? 0 : 'auto',
          left: isMobile ? 0 : 12,
          right: isMobile ? 0 : 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          padding: isMobile ? '12px 16px' : '10px 12px',
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: isMobile ? '10px 10px 0 0' : 6,
          zIndex: 5,
          pointerEvents: 'auto',
          maxHeight: isMobile ? '45vh' : 'none',
          overflowY: isMobile ? 'auto' : 'visible',
        }}
      >
        {(() => {
          const bw = isMobile ? 36 : 28;
          const bh = isMobile ? 32 : 24;
          const btnBase: React.CSSProperties = {
            width: bw,
            height: bh,
            border: '1px solid rgba(255,255,255,0.35)',
            borderRadius: 4,
            background: 'rgba(0,0,0,0.45)',
            color: '#fff',
            fontWeight: 700,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: isMobile ? 18 : 14,
          };
          return (
            <div style={{ display: 'flex', gap: isMobile ? 8 : 6, marginBottom: 8, flexWrap: 'wrap' }}>
              <button type="button" title="Zoom in" onClick={() => zoomBy(1)} style={btnBase}>+</button>
              <button type="button" title="Zoom out" onClick={() => zoomBy(-1)} style={btnBase}>-</button>
              <button
                type="button"
                title={isoLoaded ? 'Isochrones loaded' : 'Load isochrones'}
                onClick={loadIsochrones}
                style={{ ...btnBase, background: isoLoaded ? 'rgba(255,255,255,0.25)' : btnBase.background, cursor: isoLoaded ? 'default' : 'pointer', opacity: isoLoaded ? 0.5 : 1 }}
              >
                <svg viewBox="0 0 640 512" style={{ width: isMobile ? 18 : 14, height: isMobile ? 18 : 14, fill: '#fff' }}>
                  <path d="M624 352h-16V243.9c0-12.7-5.1-24.9-14.1-33.9L494 110.1c-9-9-21.2-14.1-33.9-14.1H416V48c0-26.5-21.5-48-48-48H48C21.5 0 0 21.5 0 48v320c0 26.5 21.5 48 48 48h16c0 53 43 96 96 96s96-43 96-96h128c0 53 43 96 96 96s96-43 96-96h48c8.8 0 16-7.2 16-16v-32c0-8.8-7.2-16-16-16zM160 464c-26.5 0-48-21.5-48-48s21.5-48 48-48 48 21.5 48 48-21.5 48-48 48zm320 0c-26.5 0-48-21.5-48-48s21.5-48 48-48 48 21.5 48 48-21.5 48-48 48zm80-208H416V144h44.1l99.9 99.9V256z" />
                </svg>
              </button>
              <button
                type="button"
                title={legendCollapsed ? 'Show legend' : 'Hide legend'}
                onClick={() => setLegendCollapsed((v) => !v)}
                style={btnBase}
              >
                <svg viewBox="0 0 320 512" style={{ width: isMobile ? 12 : 10, height: isMobile ? 12 : 10, fill: '#fff', transition: 'transform 0.15s', transform: legendCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>
                  <path d="M143 352.3L7 216.3c-9.4-9.4-9.4-24.6 0-33.9l22.6-22.6c9.4-9.4 24.6-9.4 33.9 0L160 256.4l96.4-96.4c9.4-9.4 24.6-9.4 33.9 0l22.6 22.6c9.4 9.4 9.4 24.6 0 33.9l-136 136c-9.2 9.4-24.4 9.4-33.9 0z"/>
                </svg>
              </button>
              <button
                type="button"
                title={dashpanelHidden ? 'Show panel' : 'Hide panel'}
                onClick={() => setDashpanelHidden((v) => !v)}
                style={btnBase}
              >
                <svg viewBox="0 0 192 512" style={{ width: isMobile ? 10 : 8, height: isMobile ? 14 : 12, fill: '#fff', transition: 'transform 0.15s', transform: dashpanelHidden ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                  <path d="M0 384.662V127.338c0-17.818 21.543-26.741 34.142-14.142l128.662 128.662c7.81 7.81 7.81 20.474 0 28.284L34.142 398.804C21.543 411.404 0 402.48 0 384.662z"/>
                </svg>
              </button>
            </div>
          );
        })()}
        {!legendCollapsed && LEGEND_ITEMS.map((item) => (
          <div key={item.key}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                minWidth: 210,
                opacity: hiddenCategories.has(item.key) ? 0.35 : 1,
                transition: 'opacity 0.15s',
              }}
            >
              {item.panels ? (
                <img
                  src={PANELS_ICON_URL}
                  alt="Panels icon"
                  width={20}
                  height={20}
                  style={{ width: '20px', height: '20px', filter: 'brightness(0) invert(1)' }}
                />
              ) : (
                <span
                  dangerouslySetInnerHTML={{
                    __html: HOUSE_ICON_SVG.replace('fill: #ff0000', `fill: ${item.color || '#888888'}`),
                  }}
                  style={{ width: 20, height: 20, display: 'block' }}
                />
              )}
              <span style={{ color: '#ffffff', fontSize: 12 }}>{item.label}</span>
              <button
                type="button"
                onClick={() => toggleCategory(item.key)}
                style={{
                  marginLeft: 'auto',
                  width: 18,
                  height: 18,
                  border: '1px solid rgba(255,255,255,0.35)',
                  borderRadius: 3,
                  background: hiddenCategories.has(item.key) ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.25)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  color: '#fff',
                  padding: 0,
                  lineHeight: 1,
                }}
                title={hiddenCategories.has(item.key) ? `Show ${item.label}` : `Hide ${item.label}`}
              >
                {hiddenCategories.has(item.key) ? '' : '✓'}
              </button>
              <span style={{ color: hiddenCategories.has(item.key) ? 'rgba(255,255,255,0.3)' : '#ffffff', fontSize: 12, minWidth: 24, textAlign: 'right' }}>
                {legendCounts[item.key] ?? 0}
              </span>
            </div>
            {item.key === 'panels' && (
              <div
                style={{
                  color: '#ffffff',
                  fontSize: 16.5,
                  fontWeight: 700,
                  marginLeft: 28,
                  marginTop: 2,
                  opacity: 0.85,
                }}
              >
                principal home material
              </div>
            )}
          </div>
        ))}
      </div>
      <div
        className="dashpanel"
        style={{
          position: 'absolute',
          top: isMobile ? 'auto' : 0,
          bottom: isMobile ? 0 : 'auto',
          right: isMobile ? 0 : 0,
          left: isMobile ? 0 : 'auto',
          width: isMobile ? '100%' : '20%',
          height: isMobile ? '40vh' : '100vh',
          backgroundColor: 'rgba(128, 128, 128, 0.65)',
          pointerEvents: 'auto',
          zIndex: 4,
          display: dashpanelHidden ? 'none' : 'flex',
          flexDirection: isMobile ? 'column' : 'column',
          borderRadius: isMobile ? '10px 10px 0 0' : 0,
          overflowY: isMobile ? 'auto' : 'visible',
        }}
      >
        {/* ── Header: brand + url ── */}
        <div
          style={{
            height: '15vh',
            display: 'flex',
            flexDirection: 'column',
            color: '#fff',
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.25)',
          }}
        >
          <div
            style={{
              height: '40%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderBottom: '1px solid rgba(255,255,255,0.15)',
              fontSize: 11,
              opacity: 0.6,
            }}
          >
            {selectedCompany ? selectedCompany.brand : 'click a company'}
          </div>
          <div
            style={{
              height: '40%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderBottom: '1px solid rgba(255,255,255,0.15)',
              fontSize: 15,
            }}
          >
            {selectedCompany?.brand || '—'}
          </div>
          <div
            style={{
              height: '20%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
            }}
          >
            {selectedCompany?.webpage ? (
              <a href={selectedCompany.webpage} target="_blank" rel="noopener noreferrer" style={{ color: '#ffa500', textDecoration: 'none' }}>
                {selectedCompany.webpage}
              </a>
            ) : '—'}
          </div>
        </div>

        {/* ── Viz + Description ── */}
        <div style={{ height: '25vh', display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(255,255,255,0.25)', overflow: 'hidden' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 600, overflow: 'hidden' }}>
            {selectedCompany?.vizUrls?.length ? (
              <img src={selectedCompany.vizUrls[0]} alt="viz" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
            ) : (
              <span style={{ fontSize: 11, opacity: 0.5 }}>no images</span>
            )}
          </div>
          <div
            style={{
              maxHeight: '50%',
              padding: '6px 8px',
              color: '#fff',
              fontSize: 10,
              lineHeight: 1.4,
              overflowY: 'auto',
              borderTop: '1px solid rgba(255,255,255,0.15)',
              opacity: 0.85,
            }}
          >
            {selectedCompany?.desc || <span style={{ opacity: 0.4, fontStyle: 'italic' }}>no description</span>}
          </div>
        </div>

        {/* ── Data: models, sqm, prices ── */}
        <div
          style={{
            height: '35vh',
            display: 'flex',
            flexDirection: 'column',
            color: '#fff',
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.25)',
          }}
        >
          {/* models count */}
          <div
            style={{
              height: '30%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderBottom: '1px solid rgba(255,255,255,0.15)',
            }}
          >
            <span style={{ fontSize: 28, marginRight: 8 }}>{selectedCompany?.modelsAmount ?? '—'}</span>
            <span style={{ fontSize: 11, opacity: 0.7 }}>models</span>
          </div>
          {/* sqm row */}
          <div
            style={{
              height: '40%',
              display: 'flex',
              flexDirection: 'row',
              borderBottom: '1px solid rgba(255,255,255,0.15)',
            }}
          >
            <div
              style={{
                height: '100%',
                aspectRatio: '1 / 1',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRight: '1px solid rgba(255,255,255,0.15)',
              }}
              dangerouslySetInnerHTML={{ __html: HOUSE_ICON_SVG.replace('fill: #ff0000', `fill: ${selectedCompany?.iconColor || '#888'}`) }}
            />
            <div
              style={{
                flex: 1,
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={{ height: '33%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: 13 }}>
                {formatNum(selectedCompany?.minSqm ?? null)} m²
              </div>
              <div style={{ height: '33%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: 13 }}>
                {formatNum(selectedCompany?.medianSqm ?? null)} m²
              </div>
              <div style={{ height: '33%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>
                {formatNum(selectedCompany?.maxSqm ?? null)} m²
              </div>
            </div>
            <div
              style={{
                height: '100%',
                aspectRatio: '1 / 1',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                borderLeft: '1px solid rgba(255,255,255,0.15)',
                fontSize: 9,
                opacity: 0.6,
                lineHeight: 1.6,
              }}
            >
              <div>min</div>
              <div>median</div>
              <div>max</div>
            </div>
          </div>
          {/* price row */}
          <div
            style={{
              height: '40%',
              display: 'flex',
              flexDirection: 'row',
            }}
          >
            <div
              style={{
                height: '100%',
                aspectRatio: '1 / 1',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                borderRight: '1px solid rgba(255,255,255,0.15)',
                lineHeight: 1,
              }}
            >
              <span style={{ fontSize: 28 }}>€</span>
              <span style={{ fontSize: 10, opacity: 0.6 }}>×1000</span>
            </div>
            <div
              style={{
                flex: 1,
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={{ height: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: 13 }}>
                {formatNum(selectedCompany?.minHomePriceK ?? null)}
              </div>
              <div style={{ height: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>
                {formatNum(selectedCompany?.medianUPriceK ?? null)}
              </div>
            </div>
            <div
              style={{
                height: '100%',
                aspectRatio: '1 / 1',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                borderLeft: '1px solid rgba(255,255,255,0.15)',
                fontSize: 9,
                opacity: 0.6,
                lineHeight: 1.6,
              }}
            >
              <div>min price</div>
              <div>median/m²</div>
            </div>
          </div>
        </div>

        {/* ── Footer: type, address, flag ── */}
        <div
          style={{
            height: '10vh',
            display: 'flex',
            flexDirection: 'column',
            color: '#fff',
            fontWeight: 600,
          }}
        >
          <div
            style={{
              height: '30%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderBottom: '1px solid rgba(255,255,255,0.15)',
              fontSize: 13,
            }}
          >
            {selectedCompany?.type || '—'} · {selectedCompany?.mainStructureMaterial || '—'}
          </div>
          <div
            style={{
              height: '70%',
              display: 'flex',
              flexDirection: 'row',
            }}
          >
            <div
              style={{
                flex: 1,
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={{ height: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: 10, padding: '0 4px', textAlign: 'center', overflow: 'hidden' }}>
                {selectedCompany?.address || '—'}
              </div>
              <div style={{ height: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11 }}>
                {selectedCompany?.country || '—'}{selectedCompany?.region ? ` · ${selectedCompany.region}` : ''}
              </div>
            </div>
            <div
              style={{
                height: '100%',
                aspectRatio: '1.3 / 1',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderLeft: '1px solid rgba(255,255,255,0.15)',
              }}
            >
              {selectedCompany?.flagUrl ? (
                <img src={selectedCompany.flagUrl} alt={selectedCompany.countryCode} style={{ maxHeight: '70%', maxWidth: '80%', objectFit: 'contain' }} />
              ) : (
                <span style={{ fontSize: 11, opacity: 0.5 }}>—</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
