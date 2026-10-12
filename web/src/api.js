// Thin fetch wrapper. The officer token is kept in localStorage for convenience only.
export function getToken() {
  try {
    return localStorage.getItem("paatrata.token") || "dev-token";
  } catch {
    return "dev-token";
  }
}

export function setToken(t) {
  try {
    localStorage.setItem("paatrata.token", t);
  } catch {
    /* storage unavailable: token lives only in memory */
  }
}

async function handle(res) {
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && data.detail !== undefined ? data.detail : data;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);
    throw new Error(`${res.status}: ${msg}`);
  }
  return data;
}

export const api = {
  get: (path) => fetch(`/api${path}`).then(handle),
  post: (path, body, admin = false) =>
    fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(admin ? { "X-Admin-Token": getToken() } : {}) },
      body: JSON.stringify(body ?? {}),
    }).then(handle),
  del: (path) =>
    fetch(`/api${path}`, { method: "DELETE", headers: { "X-Admin-Token": getToken() } }).then(handle),
  form: (path, formData) =>
    fetch(`/api${path}`, { method: "POST", headers: { "X-Admin-Token": getToken() }, body: formData }).then(handle),
};
