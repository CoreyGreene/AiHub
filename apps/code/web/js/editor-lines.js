// Match unchanged lines even when inserted or removed lines shift their positions.
export function lineAuthors(before, previous, after, author) {
  const oldLines = before.split("\n");
  const newLines = after.split("\n");
  const authors = new Array(newLines.length).fill(author);
  let start = 0;
  let oldEnd = oldLines.length;
  let newEnd = newLines.length;
  while (start < oldEnd && start < newEnd && oldLines[start] === newLines[start]) {
    authors[start] = previous[start];
    start++;
  }
  while (oldEnd > start && newEnd > start && oldLines[oldEnd - 1] === newLines[newEnd - 1]) {
    authors[--newEnd] = previous[--oldEnd];
  }
  if (oldEnd === start || newEnd === start) return authors;

  // Myers line diff. Limit the search so a wholesale rewrite cannot stall the editor.
  const oldCount = oldEnd - start;
  const newCount = newEnd - start;
  const trace = [];
  let frontier = new Map([[1, 0]]);
  const limit = 128;
  for (let distance = 0; distance <= limit; distance++) {
    trace.push(frontier);
    const next = new Map();
    for (let diagonal = -distance; diagonal <= distance; diagonal += 2) {
      const prior = previousDiagonal(frontier, diagonal, distance);
      let x = frontier.get(prior) + Number(prior < diagonal);
      let y = x - diagonal;
      while (x < oldCount && y < newCount && oldLines[start + x] === newLines[start + y]) {
        x++;
        y++;
      }
      if (x === oldCount && y === newCount) {
        for (let step = distance; step >= 0; step--) {
          const prior = previousDiagonal(trace[step], x - y, step);
          const prevX = trace[step].get(prior);
          const prevY = prevX - prior;
          while (x > prevX && y > prevY) authors[start + --y] = previous[start + --x];
          x = prevX;
          y = prevY;
        }
        return authors;
      }
      next.set(diagonal, x);
    }
    frontier = next;
  }

  // Keep unambiguous matching lines in large edits once the diff budget is used up.
  const locations = new Map();
  for (let i = start; i < oldEnd; i++) {
    const line = oldLines[i];
    locations.set(line, locations.has(line) ? -1 : i);
  }
  for (let i = start; i < newEnd; i++) {
    const line = newLines[i];
    const match = locations.get(line);
    if (match >= 0) {
      authors[i] = previous[match];
      locations.delete(line);
    }
  }
  return authors;
}

function previousDiagonal(frontier, diagonal, distance) {
  if (diagonal === -distance ||
      (diagonal !== distance && frontier.get(diagonal - 1) < frontier.get(diagonal + 1))) {
    return diagonal + 1;
  }
  return diagonal - 1;
}
