// Utility function to generate unique IDs
let idCounter = 0;

export function generateUniqueId(): string {
  return `${Date.now()}-${++idCounter}-${Math.random().toString(36).substr(2, 9)}`;
}

