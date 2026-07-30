export default function App() {
  return (
    <main className="app">
      <section className="hero-section">
        <p className="eyebrow">Editable fixture</p>
        <h1>Plan work with a calmer landing page</h1>
        <p className="hero-copy">
          This app starts as a normal Vite and React landing page so WebPilot can apply
          requested edits without treating the task as a defect repair.
        </p>
        <a className="cta-button" href="#contact">Talk to us</a>
      </section>

      <section className="pricing-section">
        <div className="section-heading">
          <p className="eyebrow">Pricing</p>
          <h2>Plans for focused teams</h2>
        </div>
        <div className="pricing-grid">
          <article className="pricing-card">
            <h3>Starter</h3>
            <p>$12 / user</p>
          </article>
          <article className="pricing-card">
            <h3>Pro</h3>
            <p>$29 / user</p>
          </article>
        </div>
      </section>

      <section className="contact-section" id="contact">
        <div className="section-heading">
          <p className="eyebrow">Contact</p>
          <h2>Tell us what you want to improve</h2>
        </div>
        <form className="contact-form">
          <label>
            Name
            <input name="name" type="text" autoComplete="name" />
          </label>
          <label>
            Email
            <input name="email" type="email" autoComplete="email" />
          </label>
          <label>
            Message
            <textarea name="message" rows="4" />
          </label>
          <button type="submit">Send message</button>
        </form>
      </section>
    </main>
  );
}
