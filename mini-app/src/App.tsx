import { UserProvider } from "./context/UserContext";
import { ThemeProvider } from "./context/ThemeContext";
import { MainPage } from "./pages/MainPage";
import { useTelegram } from "./hooks/useTelegram";

function AppShell() {
  useTelegram();
  return <MainPage />;
}

export default function App() {
  return (
    <ThemeProvider>
      <UserProvider>
        <AppShell />
      </UserProvider>
    </ThemeProvider>
  );
}
