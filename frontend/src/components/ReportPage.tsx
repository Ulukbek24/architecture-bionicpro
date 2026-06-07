import React, { useState } from 'react';
import { UserInfo } from '../App';

type Props = {
  user: UserInfo;
  bffUrl: string;
};

const ReportPage: React.FC<Props> = ({ user, bffUrl }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<any | null>(null);

  const downloadReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${bffUrl}/reports`, {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      setReport(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    await fetch(`${bffUrl}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    window.location.reload();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-2xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Usage Reports</h1>
          <button onClick={logout} className="text-sm underline">
            Logout
          </button>
        </div>

        <p className="mb-4 text-gray-700">
          Hello, <b>{user.name || user.username}</b>. Roles: {user.roles.join(', ')}
        </p>

        <button
          onClick={downloadReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Generating Report...' : 'Download Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {report && (
          <pre className="mt-4 p-4 bg-gray-50 rounded overflow-auto text-xs">
            {JSON.stringify(report, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
