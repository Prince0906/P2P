// Utility function to generate unique IDs
let idCounter = 0;

export function generateUniqueId(): string {
  return `${Date.now()}-${++idCounter}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Clean and validate an info hash from URL params or user input.
 * Returns the cleaned hash if valid, or null if invalid.
 * 
 * Handles:
 * - Full URLs (extracts hash from /download/HASH path)
 * - Just the hash string
 * - Arrays (from Next.js params)
 * - Query parameters and fragments
 */
export function cleanInfoHash(hash: string | string[] | undefined): string | null {
  if (!hash) return null;
  
  // Convert to string if it's an array
  let hashStr = Array.isArray(hash) ? hash[0] : String(hash);
  
  // Remove any URL encoding, whitespace
  hashStr = hashStr.trim();
  
  // If it's a full URL, extract the hash from the path
  // Example: "http://localhost:3000/download/9a439d6f..." -> "9a439d6f..."
  try {
    // Check if it looks like a URL
    if (hashStr.includes('://') || hashStr.startsWith('/download/')) {
      // Extract hash from URL path
      const urlMatch = hashStr.match(/\/download\/([0-9a-fA-F]{64})/i);
      if (urlMatch && urlMatch[1]) {
        hashStr = urlMatch[1];
      } else {
        // Try to extract any 64-char hex string from the URL
        const hexMatch = hashStr.match(/([0-9a-fA-F]{64})/i);
        if (hexMatch && hexMatch[1]) {
          hashStr = hexMatch[1];
        }
      }
    }
  } catch (e) {
    // If URL parsing fails, continue with original string
  }
  
  // Remove any query parameters or fragments that might have been included
  hashStr = hashStr.split('?')[0].split('#')[0];
  
  // Validate: must be exactly 64 hex characters
  if (hashStr.length === 64 && /^[0-9a-fA-F]{64}$/.test(hashStr)) {
    return hashStr.toLowerCase(); // Normalize to lowercase
  }
  
  return null;
}

