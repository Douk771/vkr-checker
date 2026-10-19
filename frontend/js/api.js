// API-клиент по api/openapi.yaml. Один origin, cookie ставит сервер.
import { ApiError, parseErrorResponse } from "./errors.js";

export function createApi({ fetchImpl = (...a) => fetch(...a), base = "" } = {}) {
  async function request(path, init = {}) {
    let response;
    try {
      response = await fetchImpl(base + path, { credentials: "same-origin", ...init });
    } catch (e) {
      if (e && e.name === "AbortError") throw e;
      throw new ApiError({ status: 0, code: "network", message: "Нет связи с сервисом" });
    }
    if (!response.ok) throw await parseErrorResponse(response);
    return response;
  }

  async function json(path, init) {
    const response = await request(path, init);
    return response.json();
  }

  function multipart(fields, signal) {
    const form = new FormData();
    for (const [name, file] of Object.entries(fields)) form.append(name, file, file.name);
    return { method: "POST", body: form, signal };
  }

  return {
    getHealth: () => json("/api/health"),
    login: (password) =>
      request("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      }).then(() => undefined),
    logout: () => request("/api/session", { method: "DELETE" }).then(() => undefined),
    check: (file, { signal } = {}) => json("/api/check", multipart({ file }, signal)),
    compare: (oldFile, newFile, { signal } = {}) =>
      json("/api/compare", multipart({ old: oldFile, new: newFile }, signal)),
    exportMatrix: async (payload) => {
      const response = await request("/api/export/matrix.xlsx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response.blob();
    },
  };
}
