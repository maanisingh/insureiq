import { test, expect } from "@playwright/test";

const API = "https://ai.cipherx.co.uk/api";

// Helper: register + get JWT
async function registerUser(request: any) {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@cipherx.co.uk`;
  const password = "E2eTest2026!Secure";
  const res = await request.post(`${API}/auth/register`, {
    data: { email, password, full_name: "E2E Tester" },
  });
  const body = await res.json();
  return { email, password, jwt: body.access_token, userId: body.user_id };
}

// ─────────────────────────────────────────────────────────
// 1. LANDING PAGE
// ─────────────────────────────────────────────────────────
test.describe("Landing Page", () => {
  test("renders hero, nav, agents, stats, and CTA", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/InsureIQ/);
    await expect(page.locator("nav").getByText("InsureIQ")).toBeVisible();
    await expect(page.getByText("AI-Powered Intelligence")).toBeVisible();
    await expect(page.getByRole("link", { name: /Start Free/i }).first()).toBeVisible();
    for (const agent of ["RAGAgent", "ResearchAgent", "PricingAgent", "PolicyAgent", "UnderwritingAgent"]) {
      await expect(page.getByText(agent).first()).toBeVisible();
    }
    await expect(page.getByText("547K", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Zero Hallucination" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Your Documents, Private" })).toBeVisible();
  });

  test("nav links work", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /Login/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
  });
});

// ─────────────────────────────────────────────────────────
// 2. AUTH PAGES RENDER
// ─────────────────────────────────────────────────────────
test.describe("Auth Pages", () => {
  test("login page renders form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("register page renders form", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  });

  test("forgot-password page renders", async ({ page }) => {
    await page.goto("/forgot-password");
    await expect(page.getByText("Reset password")).toBeVisible();
    await expect(page.getByRole("button", { name: /send reset token/i })).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────
// 3. API INTEGRATION
// ─────────────────────────────────────────────────────────
test.describe("API Integration", () => {
  test("register, login, profile, and cleanup", async ({ request }) => {
    const { email, password, jwt } = await registerUser(request);
    expect(jwt).toBeTruthy();

    const loginRes = await request.post(`${API}/auth/login`, { data: { email, password } });
    expect(loginRes.ok()).toBeTruthy();
    expect((await loginRes.json()).access_token).toBeTruthy();

    const profileRes = await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
    expect(profileRes.ok()).toBeTruthy();
    expect((await profileRes.json()).email).toBe(email);

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("workspaces: default created on register", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const res = await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } });
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).length).toBeGreaterThanOrEqual(1);
    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("API key: create, auth, revoke", async ({ request }) => {
    const { jwt } = await registerUser(request);

    const createRes = await request.post(`${API}/api-keys`, {
      headers: { Authorization: `Bearer ${jwt}` },
      data: { name: "e2e-key" },
    });
    expect(createRes.ok()).toBeTruthy();
    const key = await createRes.json();
    expect(key.raw_key).toMatch(/^ak_/);

    expect((await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${key.raw_key}` } })).ok()).toBeTruthy();

    expect((await request.delete(`${API}/api-keys/${key.id}`, { headers: { Authorization: `Bearer ${jwt}` } })).ok()).toBeTruthy();

    expect((await request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${key.raw_key}` } })).status()).toBe(401);

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("policies: CRUD", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    const policy = await (await request.post(`${API}/policies`, {
      headers: { Authorization: `Bearer ${jwt}` },
      data: { workspace_id: workspaceId, policy_type: "auto", policy_data: { insured: "E2E Corp" } },
    })).json();
    expect(policy.policy_number).toMatch(/^POL-/);

    const list = await (await request.get(`${API}/policies?workspace_id=${workspaceId}`, { headers: { Authorization: `Bearer ${jwt}` } })).json();
    expect(list.length).toBeGreaterThanOrEqual(1);

    expect((await request.delete(`${API}/policies/${policy.id}?workspace_id=${workspaceId}`, { headers: { Authorization: `Bearer ${jwt}` } })).ok()).toBeTruthy();

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("SSE chat streaming returns 200 text/event-stream", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    const res = await request.fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
      data: { workspace_id: workspaceId, message: "Hello" },
      maxRedirects: 0,
    });
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("text/event-stream");

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("SSE chat accepts preferred_agent and enabled_sources", async ({ request }) => {
    test.setTimeout(65_000); // RAGAgent with vector search can take >30s
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    const res = await request.fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
      data: {
        workspace_id: workspaceId,
        message: "What is liability insurance?",
        preferred_agent: "RAGAgent",
        enabled_sources: ["rag", "workspace"],
      },
      maxRedirects: 0,
    });
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("text/event-stream");

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("semantic search endpoints work", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    // Global search
    const globalRes = await request.get(`${API}/search/global?query=auto+insurance&limit=3`, {
      headers: { Authorization: `Bearer ${jwt}` },
    });
    expect(globalRes.ok()).toBeTruthy();
    const globalBody = await globalRes.json();
    expect(Array.isArray(globalBody.results)).toBeTruthy();

    // Combined search
    const bothRes = await request.post(`${API}/search`, {
      headers: { Authorization: `Bearer ${jwt}` },
      data: { query: "liability coverage", workspace_id: workspaceId, limit: 3 },
    });
    expect(bothRes.ok()).toBeTruthy();
    const bothBody = await bothRes.json();
    expect(Array.isArray(bothBody.global_results)).toBeTruthy();

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("chat history returns first_message field", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    // history endpoint returns sessions array (may be empty for new user)
    const histRes = await request.get(`${API}/chat/history?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${jwt}` },
    });
    expect(histRes.ok()).toBeTruthy();
    const histBody = await histRes.json();
    expect(Array.isArray(histBody.sessions)).toBeTruthy();
    // Each session object has the required fields
    if (histBody.sessions.length > 0) {
      const s = histBody.sessions[0];
      expect(s).toHaveProperty("session_id");
      expect(s).toHaveProperty("created_at");
      expect(s).toHaveProperty("message_count");
      // first_message is present (may be null if messages array was empty)
      expect("first_message" in s).toBeTruthy();
    }

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("generated documents endpoint works", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    // List generated docs (empty for new workspace)
    const listRes = await request.get(`${API}/gen-docs?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${jwt}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const docs = await listRes.json();
    expect(Array.isArray(docs)).toBeTruthy();

    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("document upload and extraction", async ({ request }) => {
    const { jwt } = await registerUser(request);
    const workspaceId = (await (await request.get(`${API}/workspaces`, { headers: { Authorization: `Bearer ${jwt}` } })).json())[0].id;

    const res = await request.post(`${API}/uploads`, {
      headers: { Authorization: `Bearer ${jwt}` },
      multipart: {
        workspace_id: workspaceId,
        file: {
          name: "test-doc.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("Auto insurance covers bodily injury liability and property damage."),
        },
      },
    });
    expect(res.ok()).toBeTruthy();
    const upload = await res.json();
    expect(upload.id).toBeTruthy();

    await new Promise((r) => setTimeout(r, 6000));

    const uploads = await (await request.get(`${API}/uploads?workspace_id=${workspaceId}`, { headers: { Authorization: `Bearer ${jwt}` } })).json();
    expect(uploads.length).toBeGreaterThanOrEqual(1);
    expect(uploads[0].extraction_status).toBe("done");

    await request.delete(`${API}/uploads/${upload.id}?workspace_id=${workspaceId}`, { headers: { Authorization: `Bearer ${jwt}` } });
    await request.delete(`${API}/auth/me`, { headers: { Authorization: `Bearer ${jwt}` } });
  });

  test("health endpoint", async ({ request }) => {
    const res = await request.get(`${API}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("healthy");
    expect(body.version).toBe("1.0.0");
  });
});

// ─────────────────────────────────────────────────────────
// 4. AUTHENTICATED DASHBOARD PAGES
// ─────────────────────────────────────────────────────────
test.describe("Dashboard (authenticated)", () => {
  let testEmail: string;
  let testPassword: string;

  test.beforeEach(async ({ page }) => {
    testEmail    = `dash-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@cipherx.co.uk`;
    testPassword = "DashTest2026!";

    const res = await page.request.post(`${API}/auth/register`, {
      data: { email: testEmail, password: testPassword, full_name: "Dashboard Tester" },
    });
    expect(res.status()).toBeLessThan(300);

    await page.goto("/login");
    await page.getByLabel(/email/i).fill(testEmail);
    await page.getByLabel(/password/i).first().fill(testPassword);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/(chat|$)/, { timeout: 15_000 });
  });

  test("chat page loads with quick actions, semantic search bar, and composer controls", async ({ page }) => {
    await page.goto("/chat");
    // Quick actions
    await expect(page.getByText(/New chat|Price a risk/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Price a risk")).toBeVisible();
    await expect(page.getByText("Draft a policy")).toBeVisible();
    // Chat history button
    await expect(page.getByText("Chats")).toBeVisible();
    // Semantic search bar always visible
    await expect(page.getByPlaceholder(/Semantic search/i)).toBeVisible();
    // Search mode pills
    await expect(page.getByText("Both")).toBeVisible();
    await expect(page.getByText("Global KB")).toBeVisible();
    await expect(page.getByText("My Docs").first()).toBeVisible();
    // Composer source toggles
    await expect(page.getByText("RAG").first()).toBeVisible();
    await expect(page.getByText("Web").first()).toBeVisible();
    // Agent selector
    await expect(page.getByText("Auto")).toBeVisible();
  });

  test("semantic search bar runs a real search and shows results", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("networkidle");

    const searchInput = page.getByPlaceholder(/Semantic search/i);
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill("auto insurance liability");
    await searchInput.press("Enter");

    // Results should appear (global KB has 547K records, so "auto insurance liability" will always match)
    await expect(page.getByText(/result/i)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Global").first()).toBeVisible();

    // Clear button appears — clicking it removes results
    const clearBtn = page.getByRole("button", { name: /Clear search results/i });
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();
    await expect(page.getByText(/result/i)).not.toBeVisible({ timeout: 3_000 });
  });

  test("policies page redirects to documents", async ({ page }) => {
    await page.goto("/policies");
    await expect(page).toHaveURL(/\/documents/, { timeout: 10_000 });
    await expect(page.getByRole("heading", { name: /Documents/i })).toBeVisible({ timeout: 10_000 });
  });

  test("documents page shows AI-generated docs UI", async ({ page }) => {
    await page.goto("/documents");
    await expect(page.getByRole("heading", { name: /Documents/i })).toBeVisible({ timeout: 10_000 });
    // Empty-state prompt for new workspace
    await expect(page.getByText(/No documents yet|Policy Doc|UW Memo/i).first()).toBeVisible({ timeout: 10_000 });
    // Filter pills visible — use role to avoid ambiguous text match
    await expect(page.getByRole("button", { name: "All" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Policy Doc" })).toBeVisible();
    await expect(page.getByRole("button", { name: "UW Memo" })).toBeVisible();
  });

  test("uploads page loads with dropzone", async ({ page }) => {
    await page.goto("/uploads");
    await expect(page.getByRole("heading", { name: /Uploads/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Drop files here/i)).toBeVisible();
  });

  test("/search redirects to /chat", async ({ page }) => {
    await page.goto("/search");
    await expect(page).toHaveURL(/\/chat/, { timeout: 10_000 });
    // Chat page content visible after redirect
    await expect(page.getByText("Price a risk")).toBeVisible({ timeout: 10_000 });
  });

  test("settings page shows all sections including token usage", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: /Settings/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Appearance/i)).toBeVisible();
    await expect(page.getByText("API Keys", { exact: true })).toBeVisible();
    await expect(page.getByText("Token Usage")).toBeVisible();
    await expect(page.getByText("Input tokens")).toBeVisible();
    await expect(page.getByText("Output tokens")).toBeVisible();
    await expect(page.getByText("Usage Documentation")).toBeVisible();
    await expect(page.getByText("Authentication")).toBeVisible();
    await expect(page.getByText("Chat Streaming (SSE)")).toBeVisible();
    await expect(page.getByText("Policy Management")).toBeVisible();
    await expect(page.getByText("Document Upload")).toBeVisible();
    await expect(page.getByText("Semantic Search")).toBeVisible();
  });

  test("sidebar has no Policies or Search links", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("link", { name: /^Search$/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /^Policies$/i })).toHaveCount(0);
  });

  test("sidebar navigation works", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("networkidle");

    // Documents link (AI generated docs)
    await page.getByRole("link", { name: /^Documents$/i }).click();
    await expect(page).toHaveURL(/\/documents/);

    // Uploads link (file uploads)
    await page.getByRole("link", { name: /^Uploads$/i }).click();
    await expect(page).toHaveURL(/\/uploads/);

    // Settings link
    await page.getByRole("link", { name: /Settings/i }).click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test("chat history modal shows sessions", async ({ page }) => {
    await page.goto("/chat");
    await page.getByText("Chats").click();
    await expect(page.getByRole("heading", { name: "Chat History" })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("New Chat")).toBeVisible();
  });
});
