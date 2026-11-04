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
  try {
    return { status: response.status, body: text ? JSON.parse(text) : null };
  } catch {
    return { status: response.status, body: text };
  }
}

export default function TenantPage() {
  const [policies, setPolicies] = useState([]);
  const [agents, setAgents] = useState([]);
  const [tools, setTools] = useState([]);
  const [documentText, setDocumentText] = useState('{"metadata":{"agent_name":"Draft"}}');
  const [policyId, setPolicyId] = useState("");
  const [reasons, setReasons] = useState("");
  const [agentId, setAgentId] = useState("");
  const [task, setTask] = useState("record the note");
  const [evaluation, setEvaluation] = useState(null);
  const [approvalId, setApprovalId] = useState("");
  const [voteResult, setVoteResult] = useState(null);

  async function refresh() {
    setPolicies((await call("/tenant/v1/policies")).body || []);
    setAgents((await call("/tenant/v1/agents")).body || []);
    setTools((await call("/tenant/v1/tools")).body || []);
  }

  async function draft() {
    const result = await call("/tenant/v1/policies", {
      method: "POST",
      body: JSON.stringify({ name: "console-draft", document: JSON.parse(documentText) }),
    });
    setReasons(JSON.stringify(result.body, null, 2));
    if (result.body && result.body.id) setPolicyId(result.body.id);
  }

  async function activate() {
    const result = await call(`/tenant/v1/policies/${policyId}/activate`, { method: "POST" });
    setReasons(JSON.stringify(result.body, null, 2));
  }

  async function evaluate(event) {
    event.preventDefault();
    const result = await call(`/tenant/v1/agents/${agentId}/evaluate`, {
      method: "POST",
      body: JSON.stringify({ task }),
    });
    setEvaluation(result.body);
  }

  async function vote(decision) {
    const result = await call(`/tenant/v1/approvals/${approvalId}/votes`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
    setVoteResult(result.body);
  }

  return (
    <main>
      <h1>Tenant console</h1>
      <p><a href="/">Operator home</a></p>
      <button type="button" onClick={refresh}>Refresh policies, agents, and tools</button>
      <h2>Policies</h2>
      <pre>{JSON.stringify(policies, null, 2)}</pre>
      <textarea value={documentText} onChange={(event) => setDocumentText(event.target.value)} rows={8} cols={70} />
      <div>
        <button type="button" onClick={draft}>Draft</button>
        <input value={policyId} onChange={(event) => setPolicyId(event.target.value)} placeholder="policy id" />
        <button type="button" onClick={activate}>Activate</button>
      </div>
      <pre>{reasons}</pre>
      <h2>Agents and tools</h2>
      <pre>{JSON.stringify({ agents, tools }, null, 2)}</pre>
      <h2>Evaluate</h2>
      <form onSubmit={evaluate}>
        <input value={agentId} onChange={(event) => setAgentId(event.target.value)} placeholder="agent id" />
        <input value={task} onChange={(event) => setTask(event.target.value)} />
        <button type="submit">Evaluate</button>
      </form>
      <pre>{evaluation ? JSON.stringify(evaluation, null, 2) : ""}</pre>
      <h2>Approval vote</h2>
      <input value={approvalId} onChange={(event) => setApprovalId(event.target.value)} placeholder="approval id" />
      <button type="button" onClick={() => vote("APPROVED")}>Approve</button>
      <button type="button" onClick={() => vote("REJECTED")}>Reject</button>
      <pre>{voteResult ? JSON.stringify(voteResult, null, 2) : ""}</pre>
    </main>
  );
}
