import React from "react";

export default function CounterControls({ onIncrement }) {
  function handleClick() {
    // BUG: the component receives the callback but never calls it.
    onIncrement;
  }

  return (
    <button
      data-testid="increment-button"
      className="button"
      onClick={handleClick}
    >
      Increment
    </button>
  );
}
