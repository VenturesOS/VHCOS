/**
 * Generate LinkedIn share URL for a job posting.
 * Uses LinkedIn's feed share with pre-filled text.
 */
export function getLinkedInShareUrl(job) {
  const jobUrl = `${window.location.origin}/jobs/${job.id}`;
  const title = job.title || 'New Job Opening';
  const company = job.public_company_alias || job.display_company || '';
  const location = job.location || '';

  let text = `We're hiring: ${title}`;
  if (company) text += ` at ${company}`;
  if (location) text += ` (${location})`;
  text += `\n\nApply now: ${jobUrl}`;

  return `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`;
}

/**
 * Open LinkedIn share window for a job.
 */
export function shareJobOnLinkedIn(job) {
  window.open(getLinkedInShareUrl(job), '_blank', 'width=600,height=600');
}
