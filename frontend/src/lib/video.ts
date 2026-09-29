/**
 * Explain why a <video> failed to load. Browsers report a missing file and an unsupported codec
 * with the same error, so ask the server for the first byte to tell them apart.
 */
export async function diagnoseVideoError(url: string): Promise<string> {
  try {
    const res = await fetch(url, { headers: { Range: 'bytes=0-0' } });
    if (res.status === 404) {
      return 'The video file is missing on the server (it may have been moved or deleted).';
    }
    if (res.ok) {
      return (
        "This browser can't decode the video's format (e.g. HEVC/H.265 from iPhones, or MPEG-4 Part 2). " +
        'Analysis results are unaffected; re-export the clip as H.264 MP4 to play it here.'
      );
    }
    return `The server could not provide the video (HTTP ${res.status}).`;
  } catch {
    return 'Could not reach the backend to load the video.';
  }
}
