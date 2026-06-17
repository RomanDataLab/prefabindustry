'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

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
  vizUrls: string[];
  planUrls: string[];
  flagUrl: string;
  iconColor: string;
}

interface DashboardPayload {
  count: number;
  companies: DashboardCompany[];
}

const HOUSE_ICON_PATH = 'M575.8 255.5c0 18-15 32.1-32 32.1h-32l.7 160.2c0 2.7-.2 5.4-.5 8.1V472c0 22.1-17.9 40-40 40H456c-1.1 0-2.2 0-3.3-.1c-1.4 .1-2.8 .1-4.2 .1H416 392c-22.1 0-40-17.9-40-40V448 384c0-17.7-14.3-32-32-32H256c-17.7 0-32 14.3-32 32v64 24c0 22.1-17.9 40-40 40H160 128.1c-1.5 0-3-.1-4.5-.2c-1.2 .1-2.4 .2-3.6 .2H104c-22.1 0-40-17.9-40-40V360c0-.9 0-1.9 .1-2.8l-.1-1.8V256H32c-17 0-32-14-32-32.1c0-9 3-17 10-24L266.4 8c7-7 15-8 22-8s15 2 21 7L564.8 231.5c8 7 12 15 11 24z';

const formatNumber = (value: number | null): string => {
  if (value === null || Number.isNaN(value)) return '—';
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(1);
};

const makeHouseSvg = (color: string): string =>
  `<svg viewBox="0 0 576 512" style="width:20px;height:20px;fill:${color};"><path d="${HOUSE_ICON_PATH}"/></svg>`;

const useDashboardCompanies = () =>
  useQuery<DashboardCompany[]>({
    queryKey: ['prefab-dashboard-data'],
    queryFn: async () => {
      const response = await fetch('/prefab-dashboard-data.json');
      if (!response.ok) {
        throw new Error(`Failed to load prefab-dashboard-data.json (${response.status})`);
      }
      const payload = (await response.json()) as DashboardPayload;
      return payload.companies || [];
    },
  });

const DataCarousel = ({ title, items }: { title: string; items: string[] }) => {
  const [index, setIndex] = useState(0);
  const hasItems = items.length > 0;
  const current = hasItems ? items[index] : '';

  useEffect(() => {
    setIndex(0);
  }, [items.join('|')]);

  const prev = () => {
    if (!hasItems) return;
    setIndex((old) => (old - 1 + items.length) % items.length);
  };

  const next = () => {
    if (!hasItems) return;
    setIndex((old) => (old + 1) % items.length);
  };

  return (
    <div className="flex h-full flex-col border-b border-orange-500/30">
      <div className="flex items-center justify-between border-b border-orange-500/30 px-3 py-1 text-[10px] uppercase tracking-wide text-orange-400">
        <span>{title}</span>
        <span>{hasItems ? `${index + 1}/${items.length}` : '0/0'}</span>
      </div>
      <div className="flex flex-1 items-center gap-2 px-2 py-2">
        <button
          type="button"
          onClick={prev}
          disabled={!hasItems}
          className="h-7 w-7 rounded-full border border-orange-500/40 text-orange-300 disabled:opacity-30"
          aria-label="Previous image"
        >
          ‹
        </button>
        <div className="relative flex-1 overflow-hidden rounded-md border border-orange-500/30 bg-black/40">
          {current ? (
            <img
              src={current}
              alt={title}
              className="h-full w-full object-contain"
            />
          ) : (
            <div className="flex h-full min-h-[90px] items-center justify-center text-[11px] text-gray-400">
              No images
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={next}
          disabled={!hasItems}
          className="h-7 w-7 rounded-full border border-orange-500/40 text-orange-300 disabled:opacity-30"
          aria-label="Next image"
        >
          ›
        </button>
      </div>
      <div className="mb-1 flex items-center justify-center gap-1">
        {items.slice(0, 10).map((_, dotIndex) => (
          <button
            key={`${title}-${dotIndex}`}
            type="button"
            onClick={() => setIndex(dotIndex)}
            className={`h-1.5 w-1.5 rounded-full ${dotIndex === index ? 'bg-orange-300' : 'bg-orange-900'}`}
            aria-label={`Go to ${title} image ${dotIndex + 1}`}
          />
        ))}
      </div>
    </div>
  );
};

const ValueLabel = ({ children }: { children: ReactNode }) => (
  <div className="flex h-full items-center justify-center text-center text-[11px] uppercase text-orange-200">
    {children}
  </div>
);

export default function MapDashboard() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const isoAvailableRef = useRef<Set<string>>(new Set());

  const [config, setConfig] = useState<MapboxConfig | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<DashboardCompany | null>(null);
  const [visibleIsoIds, setVisibleIsoIds] = useState<Set<string>>(new Set());
  const [debugLastEvent, setDebugLastEvent] = useState<string>('none');
  const [debugClickCount, setDebugClickCount] = useState(0);

  const { data: companies, isLoading: isCompaniesLoading, error: companiesError } = useDashboardCompanies();
  const selectCompany = (company: DashboardCompany, source: string) => {
    setDebugLastEvent(`${source}:${company.id}`);
    setDebugClickCount((old) => old + 1);
    setSelectedCompany((current) => {
      if (!current) return company;
      if (current.id !== company.id) return company;
      return current;
    });
  };

  useEffect(() => {
    if (!companies?.length) return;
    setSelectedCompany((current) => {
      if (current) return current;
      const randomIndex = Math.floor(Math.random() * companies.length);
      return companies[randomIndex];
    });
  }, [companies]);


  const ISO_SOURCE = 'iso-all';
  const ISO_FILL = 'iso-fill';
  const COMPANY_SOURCE = 'companies-source';
  const COMPANY_LAYER = 'companies-layer';
  const COMPANY_SELECTED_LAYER = 'companies-selected-layer';

  useEffect(() => {
    fetch('/api/mapbox-config')
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err) => {
            throw new Error(err.error || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data: MapboxConfig) => {
        if (!data.MAPBOX_ACCESS_TOKEN) {
          throw new Error('Mapbox access token not found in config');
        }
        setConfig(data);
      })
      .catch((err: Error) => setMapError(err.message));
  }, []);

  const buildIsoFilter = (ids: Set<string>): any => {
    if (ids.size === 0) return ['==', ['get', 'company_id'], '__none__'];
    return ['in', ['get', 'company_id'], ['literal', Array.from(ids)]];
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(ISO_FILL)) return;
    try {
      map.setFilter(ISO_FILL, buildIsoFilter(visibleIsoIds));
    } catch {
      // map not ready
    }
  }, [visibleIsoIds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(COMPANY_SELECTED_LAYER)) return;
    const selectedId = selectedCompany?.id ?? '__none__';
    try {
      map.setFilter(COMPANY_SELECTED_LAYER, ['==', ['get', 'id'], selectedId]);
    } catch {
      // map not ready
    }
  }, [selectedCompany]);

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

  useEffect(() => {
    if (!config || !companies?.length || !mapContainer.current || mapRef.current) return;

    mapboxgl.accessToken = config.MAPBOX_ACCESS_TOKEN;

    const map = new mapboxgl.Map({
      container: mapContainer.current,
      style: config.MAPBOX_STYLE || 'mapbox://styles/mapbox/dark-v11',
      center: [8.5417, 47.3769],
      zoom: 3,
      projection: 'mercator',
    });
    mapRef.current = map;

    map.on('error', (e) => {
      setMapError(e.error?.message || 'Unknown map error');
    });

    map.on('load', () => {
      fetch('/isochrones_all.geojson')
        .then((r) => (r.ok ? r.json() : null))
        .then((geo) => {
          if (!geo?.features?.length) return;

          const ids = new Set<string>();
          for (const feature of geo.features) {
            const companyId = String(feature?.properties?.company_id || '').trim();
            if (companyId) ids.add(companyId);
          }
          isoAvailableRef.current = ids;

          map.addSource(ISO_SOURCE, { type: 'geojson', data: geo });
          const emptyFilter: any = ['==', ['get', 'company_id'], '__none__'];

          const layers = map.getStyle()?.layers || [];
          const firstSymbol = layers.find((layer) => layer.type === 'symbol')?.id;

          map.addLayer(
            {
              id: ISO_FILL,
              type: 'fill',
              source: ISO_SOURCE,
              filter: emptyFilter,
              paint: {
                'fill-color': '#ffffff',
                'fill-opacity': 0.2,
              },
            },
            firstSymbol
          );
        })
        .catch(() => {
          // keep map functional even if isochrones file is missing
        });

      const bounds = new mapboxgl.LngLatBounds();
      const companyIndex = new Map<string, DashboardCompany>();
      const companyFeatureCollection: GeoJSON.FeatureCollection<GeoJSON.Point> = {
        type: 'FeatureCollection',
        features: companies.map((company) => {
          companyIndex.set(company.id, company);
          bounds.extend([company.longitude, company.latitude]);
          return {
            type: 'Feature',
            properties: {
              id: company.id,
              iconColor: company.iconColor || '#ff7f00',
            },
            geometry: {
              type: 'Point',
              coordinates: [company.longitude, company.latitude],
            },
          };
        }),
      };

      map.addSource(COMPANY_SOURCE, { type: 'geojson', data: companyFeatureCollection });

      map.addLayer({
        id: COMPANY_LAYER,
        type: 'circle',
        source: COMPANY_SOURCE,
        paint: {
          'circle-color': ['coalesce', ['get', 'iconColor'], '#ff7f00'],
          'circle-radius': 6,
          'circle-stroke-color': '#111111',
          'circle-stroke-width': 1,
          'circle-opacity': 0.95,
        },
      });

      map.addLayer({
        id: COMPANY_SELECTED_LAYER,
        type: 'circle',
        source: COMPANY_SOURCE,
        filter: ['==', ['get', 'id'], selectedCompany?.id ?? '__none__'],
        paint: {
          'circle-color': 'rgba(255,255,255,0)',
          'circle-radius': 10,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      });

      map.on('click', COMPANY_LAYER, (event) => {
        const feature = event.features?.[0];
        const id = String(feature?.properties?.id || '');
        if (!id) return;
        const company = companyIndex.get(id);
        if (!company) return;
        selectCompany(company, 'map-layer-click');
      });

      map.on('mouseenter', COMPANY_LAYER, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', COMPANY_LAYER, () => {
        map.getCanvas().style.cursor = '';
      });

      if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 40 });
    });

    return () => {
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch {
          // ignore map cleanup failures
        }
      }
      mapRef.current = null;
    };
  }, [config, companies]);

  const topError = mapError || (companiesError instanceof Error ? companiesError.message : null);

  const locationLine = useMemo(() => {
    if (!selectedCompany) return '—';
    if (selectedCompany.country && selectedCompany.region) {
      return `${selectedCompany.country} ${selectedCompany.region}`;
    }
    return selectedCompany.country || selectedCompany.region || '—';
  }, [selectedCompany]);

  return (
    <div
      className="h-screen w-screen bg-black text-white"
      style={{ fontFamily: 'Helvetica, Arial, sans-serif' }}
    >
      {topError && (
        <div className="absolute inset-x-0 top-0 z-30 bg-red-700 px-4 py-2 text-xs">
          {topError}
        </div>
      )}

      <div className="flex h-full">
        <div className="relative flex-[3]">
          <div ref={mapContainer} className="h-full w-full" />
          <div className="pointer-events-none absolute left-3 top-3 z-20 rounded border border-orange-500/50 bg-black/80 px-2 py-1 text-[11px] text-orange-200">
            debug clicks: {debugClickCount} | event: {debugLastEvent} | selected: {selectedCompany?.id || 'none'}
          </div>
          {isCompaniesLoading && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/40 text-xs text-gray-300">
              Loading dashboard data...
            </div>
          )}
        </div>

        <div className="h-full w-px bg-orange-500" />

        <div className="flex-[1] bg-black">
          <div className="grid h-full grid-rows-[15vh_20vh_25vh_30vh_10vh]">
            <div className="flex flex-col border-b border-orange-500/40 px-3 py-2">
              <div className="mb-1 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setVisibleIsoIds(new Set())}
                  className="rounded border border-orange-500/50 px-2 py-1 text-[10px] uppercase text-orange-300 hover:bg-orange-500/20"
                >
                  clear isochrones
                </button>
                <span className="text-[10px] text-orange-200">co_buttons</span>
              </div>
              <div className="flex flex-1 flex-col justify-center">
                <div className="text-center text-lg font-semibold">{selectedCompany?.brand || 'co_brand'}</div>
                <div className="mt-1 text-center text-[11px] text-orange-300">
                  {selectedCompany?.webpage ? (
                    <a href={selectedCompany.webpage} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      {selectedCompany.webpage}
                    </a>
                  ) : (
                    'co_url'
                  )}
                </div>
              </div>
            </div>

            <DataCarousel title="co_img" items={selectedCompany?.vizUrls || []} />
            <DataCarousel title="co_plan" items={selectedCompany?.planUrls || []} />

            <div className="grid grid-rows-[30%_40%_30%] border-b border-orange-500/40 px-2 py-1">
              <div className="flex items-center justify-center border-b border-orange-500/30">
                <div className="text-center">
                  <div className="text-[32px] font-bold leading-none">{selectedCompany?.modelsAmount ?? '—'}</div>
                  <div className="text-[12px] uppercase tracking-wide text-orange-200">models</div>
                </div>
              </div>

              <div className="grid grid-cols-[64px_1fr_70px] border-b border-orange-500/30">
                <div className="flex items-center justify-center border-r border-orange-500/30">
                  <div
                    dangerouslySetInnerHTML={{
                      __html: makeHouseSvg(selectedCompany?.iconColor || '#ff7f00'),
                    }}
                  />
                </div>
                <div className="grid grid-rows-3">
                  <div className="flex items-center justify-center border-b border-orange-500/20 text-[14px]">
                    {formatNumber(selectedCompany?.minSqm ?? null)}
                  </div>
                  <div className="flex items-center justify-center border-b border-orange-500/20 text-[14px]">
                    {formatNumber(selectedCompany?.medianSqm ?? null)}
                  </div>
                  <div className="flex items-center justify-center text-[14px]">
                    {formatNumber(selectedCompany?.maxSqm ?? null)}
                  </div>
                </div>
                <div className="border-l border-orange-500/30">
                  <ValueLabel>
                    min
                    <br />
                    median
                    <br />
                    max
                  </ValueLabel>
                </div>
              </div>

              <div className="grid grid-cols-[64px_1fr_105px]">
                <div className="flex items-center justify-center border-r border-orange-500/30">
                  <div className="text-center leading-tight text-orange-200">
                    <div className="text-[32px] font-bold">€</div>
                    <div className="text-[26px] font-bold">1000</div>
                  </div>
                </div>
                <div className="grid grid-rows-2">
                  <div className="flex items-center justify-center border-b border-orange-500/20 text-[14px]">
                    {formatNumber(selectedCompany?.minHomePriceK ?? null)}
                  </div>
                  <div className="flex items-center justify-center text-[14px]">
                    {formatNumber(selectedCompany?.medianUPriceK ?? null)}
                  </div>
                </div>
                <div className="border-l border-orange-500/30">
                  <ValueLabel>
                    min price
                    <br />
                    median price
                    <br />
                    per m2
                  </ValueLabel>
                </div>
              </div>
            </div>

            <div className="grid grid-rows-[30%_70%] px-2 py-1">
              <div className="flex items-center justify-center border-b border-orange-500/30 text-[24px] font-semibold">
                {selectedCompany?.type || 'co_matname'}
              </div>
              <div className="grid grid-cols-[1fr_100px]">
                <div className="grid grid-rows-2">
                  <div className="flex items-center justify-center border-b border-orange-500/20 px-2 text-center text-[12px]">
                    {selectedCompany?.address || 'co_locaddress'}
                  </div>
                  <div className="flex items-center justify-center px-2 text-center text-[12px]">
                    {locationLine}
                  </div>
                </div>
                <div className="flex items-center justify-center border-l border-orange-500/30">
                  {selectedCompany?.flagUrl ? (
                    <img src={selectedCompany.flagUrl} alt={selectedCompany.countryCode} className="max-h-10 max-w-[70px] object-contain" />
                  ) : (
                    <span className="text-[12px] text-gray-400">co_flag</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

