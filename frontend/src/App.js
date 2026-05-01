import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "./components/Layout";
import KeysModal from "./components/KeysModal";
import Dashboard from "./pages/Dashboard";
import BrandNew from "./pages/BrandNew";
import BrandDetail from "./pages/BrandDetail";
import Templates from "./pages/Templates";
import Settings from "./pages/Settings";
import Gallery from "./pages/Gallery";
import { keysStore } from "./lib/api";

function App() {
  const [keysOpen, setKeysOpen] = useState(false);

  useEffect(() => {
    if (!keysStore.has()) setKeysOpen(true);
  }, []);

  const open = () => setKeysOpen(true);

  return (
    <div className="App">
      <BrowserRouter>
        <Layout onOpenKeys={open}>
          <Routes>
            <Route path="/" element={<Dashboard onOpenKeys={open} />} />
            <Route path="/brands/new" element={<BrandNew onOpenKeys={open} />} />
            <Route path="/brands/:id" element={<BrandDetail onOpenKeys={open} />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/gallery" element={<Gallery />} />
          </Routes>
        </Layout>
        <KeysModal open={keysOpen} onClose={() => setKeysOpen(false)} />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              borderRadius: 0,
              border: "1px solid #000",
              background: "#fff",
              color: "#000",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "12px",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            },
          }}
        />
      </BrowserRouter>
    </div>
  );
}

export default App;
