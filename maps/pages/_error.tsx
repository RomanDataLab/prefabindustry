import { NextPageContext } from 'next';
import Error from 'next/error';

interface ErrorProps {
  statusCode: number;
  hasGetInitialPropsRun?: boolean;
  err?: Error;
}

function ErrorPage({ statusCode }: ErrorProps) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      backgroundColor: '#000',
      color: '#fff',
      flexDirection: 'column'
    }}>
      <h1>{statusCode || 'Error'}</h1>
      <p>
        {statusCode === 404
          ? 'This page could not be found.'
          : 'An error occurred on server'}
      </p>
    </div>
  );
}

ErrorPage.getInitialProps = ({ res, err }: NextPageContext) => {
  const statusCode = res ? res.statusCode : err ? err.statusCode : 404;
  return { statusCode };
};

export default ErrorPage;
