export function colorForState(state) {
  const colors = {
    provisioning: "red",
    initializing: "orange",
    ready: "green",
    error: "red",
  };
  if (!Object.hasOwn(colors, state)) throw new Error(`Unknown sandbox state: ${state}`);
  return colors[state];
}

export function summarize(items) {
  const counts = { total: items.length, provisioning: 0, initializing: 0, ready: 0, error: 0 };
  for (const item of items) {
    colorForState(item.state);
    counts[item.state] += 1;
  }
  return counts;
}
