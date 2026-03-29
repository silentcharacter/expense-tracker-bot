import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { UserProvider } from "./context/UserContext";
import { ThemeProvider } from "./context/ThemeContext";
import { Header } from "./components/layout/Header";
import { TabBar } from "./components/layout/TabBar";
import { PageTransition } from "./components/layout/PageTransition";
import { DashboardPage } from "./pages/DashboardPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BudgetPage } from "./pages/BudgetPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useTelegram } from "./hooks/useTelegram";

function AppShell() {
  useTelegram();

  const location = useLocation();

  return (
    <div
      style={{
        height: "100dvh",
        backgroundColor: "var(--app-bg)",
        color: "var(--app-text-primary)",
      }}
    >
      <Header />
      <PageTransition pageKey={location.pathname}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/budget" element={<BudgetPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </PageTransition>
      <TabBar />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <UserProvider>
        <HashRouter>
          <AppShell />
        </HashRouter>
      </UserProvider>
    </ThemeProvider>
  );
}
