export default function App() {
  function handleTabClick() {
    // Intentional fixture bug: clicking a tab does not update the active panel.
  }

  return (
    <main className="app">
      <section className="tabs-card" aria-labelledby="tabs-title">
        <p className="eyebrow">Buggy fixture</p>
        <h1 id="tabs-title">Project workspace tabs</h1>
        <div className="tab-list" role="tablist" aria-label="Project sections">
          <button type="button" role="tab" aria-selected="true" onClick={handleTabClick}>
            Overview
          </button>
          <button type="button" role="tab" aria-selected="false" onClick={handleTabClick}>
            Details
          </button>
        </div>
        <section className="tab-panel panel-active" role="tabpanel">
          <h2>Overview</h2>
          <p>The overview panel is visible by default.</p>
        </section>
        <section className="tab-panel" role="tabpanel" hidden>
          <h2>Details</h2>
          <p>The details panel should appear after clicking the Details tab.</p>
        </section>
      </section>
    </main>
  );
}
