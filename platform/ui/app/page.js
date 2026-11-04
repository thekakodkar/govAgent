"use client";

import { useState } from "react";

const api = process.env.NEXT_PUBLIC_PLATFORM_API || "http://127.0.0.1:8070";

async function call(path, options) {
  const response = await fetch(`${api}${path}`, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let body = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { status: response.status, body };
}

export default function HomePage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenants, setTenants] = useState(null);
  const [message, setMessage] = useState("");

  async function login(event) {
    event.preventDefault();
    const result = await call("/platform/v1/session", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setMessage(result.status === 200 ? `Signed in as ${result.body.scope}` : "Login failed");
  }

  async function loadTenants() {
    const result = await call("/platform/v1/tenants");
    setTenants(result.body);
  }

  return (
    <main>
      <h1>Platform operator</h1>
      <form onSubmit={login}>
        <label>
          Email <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button type="submit">Sign in</button>
      </form>
      <p>{message}</p>
      <button type="button" onClick={loadTenants}>Load tenants</button>
      <pre>{tenants ? JSON.stringify(tenants, null, 2) : ""}</pre>
      <p><a href="/tenant">Tenant policy console</a></p>
    </main>
  );
}
