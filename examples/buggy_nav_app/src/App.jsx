export default function App() {
  function handleMenuClick() {
    // Intentional fixture bug: the click handler does not open the menu.
  }

  return (
    <main className="app">
      <header className="topbar">
        <h1>Navigation Fixture</h1>
        <button type="button" aria-label="Open menu" onClick={handleMenuClick}>
          Menu
        </button>
      </header>
      <nav className="nav-menu" aria-label="Primary navigation">
        <a href="#overview">Overview</a>
        <a href="#reports">Reports</a>
        <a href="#settings">Settings</a>
      </nav>
      <section id="overview" className="content">
        <h2>Overview</h2>
        <p>The menu links should become visible after the menu button is clicked.</p>
      </section>
    </main>
  );
}

