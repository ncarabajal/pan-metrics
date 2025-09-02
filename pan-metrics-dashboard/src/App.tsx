import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DevicesTable from "./components/DevicesTable";
import "./index.css";          // ← keep, even if Tailwind isn't installed yet

const qc = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <main className="max-w-6xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">Firewall-Health Dashboard</h1>
        <DevicesTable />
      </main>
    </QueryClientProvider>
  );
}
