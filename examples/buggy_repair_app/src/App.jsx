export default function App() {
  return (
    <main className="app">
      <section className="hero-section">
        <p className="eyebrow">Buggy fixture</p>
        <h1>Task management should feel calm</h1>
        <p>Use this intentionally broken app to verify browser-grounded repair.</p>
        <button type="button">Start planning</button>
      </section>

      <section className="pricing-section">
        <h2>Pricing</h2>
        <div className="pricing-grid">
          <article>
            <h3>Starter</h3>
            <p>$12 / user</p>
          </article>
          <article>
            <h3>Pro</h3>
            <p>$29 / user</p>
          </article>
        </div>
      </section>

      <section className="contact-section">
        <h2>Contact</h2>
        <form className="contact-form">
          <label>
            Name
            <input name="name" type="text" />
          </label>
          <label>
            Email
            <input name="email" type="email" />
          </label>
          <button type="submit">Send message</button>
        </form>
      </section>

      <div className="wide-banner">This wide element intentionally causes mobile overflow.</div>
    </main>
  );
}

