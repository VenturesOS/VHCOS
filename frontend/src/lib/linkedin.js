/**
 * Generate LinkedIn share URL for a job posting.
 * Uses LinkedIn's share-offsite URL (no API needed).
 */
export function getLinkedInShareUrl(job) {
  const jobUrl = `https://ventureshrd.com/jobs/${job.id}`;
  return `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(jobUrl)}`;
}

/**
 * Open LinkedIn share window for a job.
 */
export function shareJobOnLinkedIn(job) {
  window.open(getLinkedInShareUrl(job), '_blank', 'width=600,height=600');
}
