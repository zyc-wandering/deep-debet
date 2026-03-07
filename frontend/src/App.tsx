import { useDebateStore } from "./store/debateStore";
import { useDebate } from "./hooks/useDebate";
import { ConfigPage } from "./pages/ConfigPage";
import { DebateRoomPage } from "./pages/DebateRoomPage";
import { DebateStartRequest } from "./types";

function App() {
  const currentTab = useDebateStore((s) => s.currentTab);
  const status = useDebateStore((s) => s.status);
  const debate = useDebate();

  const handleStart = async (payload: DebateStartRequest) => {
    await debate.start(payload);
  };

  const handleStop = async () => {
    await debate.stop();
  };

  // Show config page when in config tab
  if (currentTab === "config") {
    return (
      <ConfigPage
        onStart={handleStart}
        isRunning={status === "running"}
      />
    );
  }

  // Show debate room for all other tabs
  return (
    <DebateRoomPage
      onStop={handleStop}
    />
  );
}

export default App;
