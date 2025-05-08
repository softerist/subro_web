// frontend/src/App.tsx
import { useState } from "react";
import "./App.css"; // Assuming you have a basic App.css from Vite init

function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Subtitle Downloader App Frontend</h1>
        <p>Vite + React + TypeScript is Running!</p>
        <p>
          <button onClick={() => setCount((count) => count + 1)}>
            Count is: {count}
          </button>
        </p>
        <p>
          Edit <code>frontend/src/App.tsx</code> and save to test HMR.
        </p>
        <a
          className="App-link"
          href="https://reactjs.org"
          target="_blank"
          rel="noopener noreferrer"
        >
          Learn React
        </a>
        {" | "}
        <a
          className="App-link"
          href="https://vitejs.dev/guide/features.html"
          target="_blank"
          rel="noopener noreferrer"
        >
          Vite Docs
        </a>
      </header>
    </div>
  );
}

export default App;
