import Map from '../components/Map';
import Head from 'next/head';

export default function Home() {
  return (
    <>
      <Head>
        <title>Prefab World Map</title>
        <meta name="description" content="Map showing prefab companies worldwide" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
      </Head>
      <main style={{ margin: 0, padding: 0, minHeight: '100vh', width: '100%' }}>
        <Map />
      </main>
    </>
  );
}
