// Helpers for the tags page: the rules the server applies to a tag, checked before a request.

export interface ITagDraft {
  name: string;
  color: string | null;
  description: string;
}

// The message for the first problem with a tag, or null when the tag can be sent.
export function validateTag(tag: ITagDraft): string | null {
  if (!tag.name.trim()) {
    return 'A tag needs a name.';
  }
  if (tag.name.trim().length > 64) {
    return 'A tag name is at most 64 characters.';
  }
  if (tag.description.length > 2000) {
    return 'A description is at most 2000 characters.';
  }
  return null;
}

// The colour as the server stores it: "#rrggbb" in lower case. An empty value means no colour
// (null). Anything else is undefined, which the caller reports.
export function normalizeColor(value: string): string | null | undefined {
  const trimmed = value.trim();
  if (trimmed === '') {
    return null;
  }
  return /^#[0-9a-fA-F]{6}$/.test(trimmed) ? trimmed.toLowerCase() : undefined;
}
