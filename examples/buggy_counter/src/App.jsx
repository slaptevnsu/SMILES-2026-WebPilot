import React, { useState } from "react";

export default function App() {
  const [count, setCount] = useState(0);

  function handleIncrement() {
    // BUG: this handler does not update React state.
    count + 1;
  }

  return (
    <main className="page">
      <section className="card" aria-labelledby="counter-title">
        <p className="eyebrow">WebPilot diagnostic repair demo</p>
        <h1 id="counter-title">Buggy Counter</h1>
        <p className="description">
          The button is visible, but the counter value does not increase when clicked.
        </p>

        <div className="counter-panel">
          <span className="label">Current count</span>
          <strong className="count-value" data-testid="count-value">
            {count}
          </strong>
        </div>

        <button className="button" data-testid="increment-button" onClick={handleIncrement}>
          Increase count
        </button>
      </section>
    </main>
  );
}
