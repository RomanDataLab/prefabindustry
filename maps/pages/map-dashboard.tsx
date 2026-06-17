import Head from 'next/head';
import dynamic from 'next/dynamic';

const MapDashboard = dynamic(() => import('../components/MapDashboard'), {
  ssr: false,
});

export default function MapDashboardPage() {
  return (
    <>
      <Head>
        <title>Prefab Map Dashboard</title>
        <meta
          name="description"
          content="Interactive prefab world map with data dashboard"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <MapDashboard />
    </>
  );
}

