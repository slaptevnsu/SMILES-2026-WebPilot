import React, { useState } from "react";

export default function App() {
  const [message, setMessage] = useState("");

  function handleChange(event) {
    // BUG: this handler reads the value but does not update React state.
    event.target.value;
  }

  return (
    <main className="app">
      <section className="card">
        <p className="eyebrow">Input Echo Demo</p>
        <h1>Type a message</h1>

        <label className="label" htmlFor="message-input">
          Message
        </label>
        <input
          id="message-input"
          className="input"
          data-testid="echo-input"
          value={message}
          onChange={handleChange}
          placeholder="Type something"
        />

        <div className="preview-box">
          <p className="preview-label">Preview</p>
          <p className="preview-value" data-testid="echo-preview">
            {message}
          </p>
        </div>
      </section>
    </main>
  );
}
