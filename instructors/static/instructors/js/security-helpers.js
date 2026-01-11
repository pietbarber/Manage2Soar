/**
 * Security helper functions for the instructors app.
 * Shared across qualification forms to avoid code duplication.
 */

/**
 * Validate URL is safe (relative path, http/https, or limited data:image/* formats)
 * @param {string} url - The URL to validate
 * @returns {boolean} - True if the URL is safe to use as an image source
 */
function isSafeImageUrl(url) {
  if (!url || typeof url !== 'string') return false;
  url = url.trim();
  if (!url) return false;

  // Allow relative paths (no protocol)
  if (url.startsWith('/') || url.startsWith('./')) return true;

  // Allow http/https URLs
  if (url.startsWith('http://') || url.startsWith('https://')) return true;

  // Allow only specific safe data: URLs for inline images (explicitly exclude SVG)
  const lowerUrl = url.toLowerCase();
  if (lowerUrl.startsWith('data:image/')) {
    const allowedDataPrefixes = [
      'data:image/png;',
      'data:image/png,',
      'data:image/jpeg;',
      'data:image/jpeg,',
      'data:image/jpg;',
      'data:image/jpg,',
      'data:image/gif;',
      'data:image/gif,',
      'data:image/webp;',
      'data:image/webp,',
    ];

    for (const prefix of allowedDataPrefixes) {
      if (lowerUrl.startsWith(prefix)) {
        return true;
      }
    }

    // Any other data:image/* (including SVG) is not allowed
    return false;
  }

  return false;
}

/**
 * Sanitizes text for use in HTML attributes.
 * Uses the browser's built-in escaping via textContent/innerHTML,
 * which is more robust than manual string replacement.
 * Note: This is defense-in-depth; textContent is already safe text.
 * @param {string} text - The text to sanitize
 * @returns {string} - Sanitized text safe for attribute values
 */
function escapeForAttribute(text) {
  if (typeof text !== 'string') return '';
  // Use DOM-based escaping - more robust than manual replacement
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
