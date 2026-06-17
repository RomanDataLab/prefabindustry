import type { AppProps } from 'next/app';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import 'mapbox-gl/dist/mapbox-gl.css';
import '../styles/globals.css';
import PopupStyleInject from '../components/PopupStyleInject';

const queryClient = new QueryClient();

export default function App({ Component, pageProps }: AppProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <PopupStyleInject />
      <Component {...pageProps} />
    </QueryClientProvider>
  );
}
