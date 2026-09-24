const VERSION_PREFIX = /^(\d+)\.(\d+)\.(\d+)/;
const PRERELEASE_PATTERN = /^\d+\.\d+\.\d+-(?:beta|rc)/i;

function versionTuple(value: string): [number, number, number] | null {
  const match = VERSION_PREFIX.exec(value || "");

  if (match === null) {
    return null;
  }

  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function isPrerelease(value: string): boolean {
  return PRERELEASE_PATTERN.test(value || "");
}

/** Whether latest is a release newer than the running version. */
export function isNewerVersion(current: string, latest: string): boolean {
  const currentTuple = versionTuple(current);
  const latestTuple = versionTuple(latest);

  if (currentTuple === null || latestTuple === null) {
    return false;
  }

  if (
    currentTuple[0] === latestTuple[0] &&
    currentTuple[1] === latestTuple[1] &&
    currentTuple[2] === latestTuple[2]
  ) {
    return isPrerelease(current) && !isPrerelease(latest);
  }

  if (latestTuple[0] !== currentTuple[0]) {
    return latestTuple[0] > currentTuple[0];
  }

  if (latestTuple[1] !== currentTuple[1]) {
    return latestTuple[1] > currentTuple[1];
  }

  return latestTuple[2] > currentTuple[2];
}
