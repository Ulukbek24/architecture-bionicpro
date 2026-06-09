import React, { useEffect, useState } from 'react';
import ReportPage from './components/ReportPage';

export type UserInfo = {
  sub: string;
  username: string;
  email: string;
  name: string;
  roles: string[];
  prosthetic_ids: string[];
};

const BFF_URL = process.env.REACT_APP_BFF_URL || 'http://localhost:8000';

const App: React.FC = () => {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BFF_URL}/me`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setUser(data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100 gap-3">
        <a
          href={`${BFF_URL}/auth/login`}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </a>
        <a
          href={`${BFF_URL}/auth/login?idp=yandex`}
          className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
        >
          Login with Yandex ID
        </a>
      </div>
    );
  }

  return (
    <div className="App">
      <ReportPage user={user} bffUrl={BFF_URL} />
    </div>
  );
};

export default App;
