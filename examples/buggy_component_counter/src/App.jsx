import React, { useState } from "react";
import CounterControls from "./components/CounterControls.jsx";
import "./App.css";

export default function App() {
  const [count, setCount] = useState(0);

  function handleIncrement() {
    setCount((currentCount) => currentCount + 1);
  }

  return (
    <main className="app">
      <section className="card">
        <p className="eyebrow">Component Counter Demo</p>
        <h1>Counter</h1>

        <div className="counter-row">
          <span className="label">Current count</span>
          <span data-testid="count-value" className="count">
            {count}
          </span>
        </div>

        <CounterControls onIncrement={handleIncrement} />

        <p className="hint">
          The button is rendered by a child component.
        </p>
      </section>
    </main>
  );
}
