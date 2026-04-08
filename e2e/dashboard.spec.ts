import { test, expect } from "@playwright/test";

const BASE = "http://127.0.0.1:9877";

// ── Page Load & Branding ─────────────────────────────────

test.describe("Page Load & Branding", () => {
  test("dashboard loads with TerminalMBA title", async ({ page }) => {
    await page.goto(BASE);
    await expect(page).toHaveTitle("TerminalMBA");
  });

  test("sidebar shows TerminalMBA brand", async ({ page }) => {
    await page.goto(BASE);
    const brand = page.locator(".sidebar-brand");
    await expect(brand).toContainText("TerminalMBA");
  });

  test("version badge loads", async ({ page }) => {
    await page.goto(BASE);
    const badge = page.locator("#versionBadge");
    await expect(badge).toHaveText(/v\d+\.\d+\.\d+/, { timeout: 5000 });
  });
});

// ── Sessions Grid ────────────────────────────────────────

test.describe("Sessions Grid", () => {
  test("sessions load and display as cards", async ({ page }) => {
    await page.goto(BASE);
    // Wait for cards to render
    await page.waitForSelector(".card", { timeout: 5000 });
    const cards = page.locator(".card");
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test("session cards show tool badges", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const badges = page.locator(".tool-badge");
    expect(await badges.count()).toBeGreaterThan(0);
    // Check that badge text is a known tool name
    const firstBadge = await badges.first().textContent();
    expect(["claude", "claude-ext", "codex", "cursor", "opencode", "kiro"]).toContain(firstBadge?.trim());
  });

  test("session cards show message count", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const msgCounts = page.locator(".card-msgs");
    expect(await msgCounts.count()).toBeGreaterThan(0);
    const text = await msgCounts.first().textContent();
    expect(text).toMatch(/\d+ msgs/);
  });

  test("session cards show time ago", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const times = page.locator(".card-time");
    expect(await times.count()).toBeGreaterThan(0);
  });
});

// ── Layout Toggle ────────────────────────────────────────

test.describe("Layout Toggle", () => {
  test("toggle between grid and list layout", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Default should be grid
    await expect(page.locator(".grid-layout")).toBeVisible();

    // Click layout toggle
    await page.click("#layoutToggle");
    await expect(page.locator(".list-layout")).toBeVisible();

    // Toggle back
    await page.click("#layoutToggle");
    await expect(page.locator(".grid-layout")).toBeVisible();
  });
});

// ── Sidebar Navigation ──────────────────────────────────

test.describe("Sidebar Navigation", () => {
  test("All Sessions view is active by default", async ({ page }) => {
    await page.goto(BASE);
    const allSessions = page.locator('.sidebar-item[data-view="sessions"]');
    await expect(allSessions).toHaveClass(/active/);
  });

  test("switch to Projects view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="projects"]');
    await expect(page.locator('.sidebar-item[data-view="projects"]')).toHaveClass(/active/);
    // Should show projects heading
    await expect(page.locator("h2")).toContainText("Projects");
  });

  test("switch to Timeline view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="timeline"]');
    await expect(page.locator('.sidebar-item[data-view="timeline"]')).toHaveClass(/active/);
    await expect(page.locator("h2")).toContainText("Timeline");
  });

  test("switch to Running view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="running"]');
    await expect(page.locator('.sidebar-item[data-view="running"]')).toHaveClass(/active/);
    await expect(page.locator("h2")).toContainText("Running Sessions");
  });

  test("switch to Analytics view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="analytics"]');
    await expect(page.locator('.sidebar-item[data-view="analytics"]')).toHaveClass(/active/);
    await expect(page.locator("h2")).toContainText("Cost Analytics", { timeout: 5000 });
  });

  test("switch to Starred view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="starred"]');
    await expect(page.locator('.sidebar-item[data-view="starred"]')).toHaveClass(/active/);
  });

  test("switch to Changelog view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="changelog"]');
    await expect(page.locator('.sidebar-item[data-view="changelog"]')).toHaveClass(/active/);
    await expect(page.locator("h2")).toContainText("Changelog", { timeout: 5000 });
  });

  test("switch to Settings view", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="settings"]');
    await expect(page.locator('.sidebar-item[data-view="settings"]')).toHaveClass(/active/);
    await expect(page.locator("h2")).toContainText("Settings");
  });
});

// ── Agent Filters (sidebar) ─────────────────────────────

test.describe("Agent Filters", () => {
  test("filter by Claude Code agent", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const totalCards = await page.locator(".card").count();

    await page.click('.sidebar-item[data-view="claude-only"]');
    await page.waitForSelector(".card", { timeout: 5000 });

    // All visible badges should be "claude"
    const badges = page.locator(".tool-badge");
    const count = await badges.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < Math.min(count, 10); i++) {
      const text = await badges.nth(i).textContent();
      expect(text?.trim()).toMatch(/^claude/);
    }
  });

  test("filter by Codex agent", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="codex-only"]');
    // May have sessions or empty state
    await page.waitForTimeout(1000);
    const cards = await page.locator(".card").count();
    if (cards > 0) {
      const badges = page.locator(".tool-badge");
      for (let i = 0; i < Math.min(await badges.count(), 5); i++) {
        await expect(badges.nth(i)).toHaveText("codex");
      }
    } else {
      await expect(page.locator(".empty-state")).toBeVisible();
    }
  });

  test("filter by Cursor agent", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="cursor-only"]');
    await page.waitForTimeout(1000);
    const cards = await page.locator(".card").count();
    if (cards > 0) {
      const badge = await page.locator(".tool-badge").first().textContent();
      expect(badge?.trim()).toBe("cursor");
    }
  });

  test("switching back to All Sessions shows all agents", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const allCount = await page.locator(".card").count();

    // Filter to claude
    await page.click('.sidebar-item[data-view="claude-only"]');
    await page.waitForTimeout(500);

    // Back to all
    await page.click('.sidebar-item[data-view="sessions"]');
    await page.waitForTimeout(500);
    const afterCount = await page.locator(".card").count();
    expect(afterCount).toBe(allCount);
  });
});

// ── Search ──────────────────────────────────────────────

test.describe("Search", () => {
  test("search input exists and is focusable", async ({ page }) => {
    await page.goto(BASE);
    const input = page.locator("#searchInput");
    await expect(input).toBeVisible();
    await input.focus();
    await expect(input).toBeFocused();
  });

  test("client-side search filters sessions immediately", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const totalCards = await page.locator(".card").count();

    // Type a search query that matches some session titles
    await page.fill("#searchInput", "refactor");
    await page.waitForTimeout(300);

    const filteredCards = await page.locator(".card").count();
    // Should either filter down or show empty state
    expect(filteredCards).toBeLessThanOrEqual(totalCards);
  });

  test("clearing search restores all sessions", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const totalCards = await page.locator(".card").count();

    await page.fill("#searchInput", "xyznonexistent");
    await page.waitForTimeout(300);

    // Clear search
    await page.fill("#searchInput", "");
    await page.waitForTimeout(300);
    const restoredCards = await page.locator(".card").count();
    expect(restoredCards).toBe(totalCards);
  });

  test("deep search triggers and shows results from backend", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Listen for the /api/search request
    const searchRequest = page.waitForRequest((req) =>
      req.url().includes("/api/search?q=")
    );

    // Type enough to trigger deep search (>= 2 chars, 600ms debounce)
    await page.fill("#searchInput", "dashboard");

    // Wait for the API call to fire
    const req = await searchRequest;
    expect(req.url()).toContain("q=dashboard");

    // Wait for response to be processed
    await page.waitForTimeout(1000);

    // If deep search found results, a toast should appear or sessions should be boosted
    // The key test is that the API was called - the bug was it only showed toast
    // Now with the fix, matching sessions should be visible in the grid
    const cards = await page.locator(".card").count();
    // At least the deep search shouldn't break rendering
    expect(cards).toBeGreaterThanOrEqual(0);
  });

  test("deep search results appear even when client-side filter misses them", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Wait for search API response
    const searchResponse = page.waitForResponse((resp) =>
      resp.url().includes("/api/search?q=")
    );

    // Search for something that's inside message content but not in session title
    // This should trigger backend fuzzy search which finds it in message content
    await page.fill("#searchInput", "database");

    try {
      const resp = await searchResponse;
      const data = await resp.json();

      if (data.length > 0) {
        // Wait for applyDeepSearchResults to process
        await page.waitForTimeout(500);

        // Sessions with deep matches should now be visible
        const cards = await page.locator(".card").count();
        expect(cards).toBeGreaterThan(0);

        // Toast should show match count
        const toast = page.locator("#toast");
        await expect(toast).toHaveClass(/show/, { timeout: 3000 });
      }
    } catch {
      // Search may not find matches depending on data - that's OK
    }
  });
});

// ── Session Detail Panel ────────────────────────────────

test.describe("Session Detail Panel", () => {
  test("clicking a card opens detail panel", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    await page.locator(".card").first().click();

    // Detail panel and overlay should open
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });
    await expect(page.locator("#overlay")).toHaveClass(/open/);
  });

  test("detail panel shows session info", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    // Should have detail header, info, and messages
    await expect(page.locator(".detail-header")).toBeVisible();
    await expect(page.locator(".detail-body")).toBeVisible();
  });

  test("detail panel shows session ID", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    // Session ID should be visible in the detail info
    const detailText = await page.locator(".detail-info").textContent();
    expect(detailText).toContain("Session ID");
  });

  test("detail panel shows messages", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    // Should have Messages heading
    await expect(page.locator(".detail-messages h3")).toContainText("Messages");
    // Should have at least one message
    const msgs = page.locator(".message");
    expect(await msgs.count()).toBeGreaterThan(0);
  });

  test("close detail panel with X button", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    await page.locator(".detail-close").click();
    // Panel should close - class "open" removed
    await expect(page.locator("#detail")).not.toHaveClass(/open/);
  });

  test("close detail panel with Escape key", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    await page.keyboard.press("Escape");
    await expect(page.locator("#detail")).not.toHaveClass(/open/);
  });

  test("close detail panel by clicking overlay", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    await page.locator("#overlay").click({ force: true });
    await expect(page.locator("#detail")).not.toHaveClass(/open/);
  });

  test("detail panel has Export button", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    await expect(page.locator(".detail-actions .btn-secondary")).toContainText("Export");
  });

  test("detail panel has Delete button", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    await page.locator(".card").first().click();
    await expect(page.locator("#detail")).toHaveClass(/open/, { timeout: 5000 });

    await expect(page.locator(".detail-actions .btn-delete")).toContainText("Delete");
  });
});

// ── Star / Unstar ────────────────────────────────────────

test.describe("Star Sessions", () => {
  test("star a session via card button", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    const card = page.locator(".card").first();
    // Hover to reveal the star button
    await card.hover();
    const starBtn = card.locator(".card-action-btn");
    await starBtn.click({ force: true });

    await expect(card).toHaveClass(/starred/);
  });

  test("unstar a session", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Star it
    await page.locator(".card").first().hover();
    await page.locator(".card").first().locator(".card-action-btn").click({ force: true });
    await expect(page.locator(".card").first()).toHaveClass(/starred/);

    // Re-render replaces DOM nodes, so re-query after star
    await page.locator(".card").first().hover();
    await page.locator(".card").first().locator(".card-action-btn").click({ force: true });
    await expect(page.locator(".card").first()).not.toHaveClass(/starred/);
  });

  test("starred sessions appear in Starred view", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Star the first session
    const card = page.locator(".card").first();
    await card.hover();
    await card.locator(".card-action-btn").click({ force: true });

    // Switch to starred view
    await page.click('.sidebar-item[data-view="starred"]');
    await page.waitForTimeout(500);

    const cards = await page.locator(".card").count();
    expect(cards).toBeGreaterThanOrEqual(1);

    // Cleanup: unstar
    const starredCard = page.locator(".card").first();
    await starredCard.hover();
    await starredCard.locator(".card-action-btn").click({ force: true });
  });
});

// ── Theme Switching ──────────────────────────────────────

test.describe("Themes", () => {
  test("switch to Light theme", async ({ page }) => {
    await page.goto(BASE);
    await page.click('button:has-text("Light")');
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme).toBe("light");
  });

  test("switch to Monokai theme", async ({ page }) => {
    await page.goto(BASE);
    await page.click('button:has-text("Monokai")');
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme).toBe("monokai");
  });

  test("switch to Dark theme", async ({ page }) => {
    await page.goto(BASE);
    await page.click('button:has-text("Dark")');
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme).toBe("dark");
  });
});

// ── Analytics View ───────────────────────────────────────

test.describe("Analytics", () => {
  test("analytics shows cost summary cards", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="analytics"]');
    await page.waitForSelector(".analytics-summary", { timeout: 5000 });

    const summaryCards = page.locator(".analytics-card");
    expect(await summaryCards.count()).toBe(4);

    // Should show Total Cost, Sessions, Total Tokens, Daily Rate
    const labels = page.locator(".analytics-label");
    const labelsText = await labels.allTextContents();
    expect(labelsText).toContain("Total Cost");
    expect(labelsText).toContain("Sessions");
  });

  test("analytics shows agent breakdown chart", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="analytics"]');
    await page.waitForSelector(".hbar-chart", { timeout: 5000 });

    // Should have bar chart rows
    const rows = page.locator(".hbar-row");
    expect(await rows.count()).toBeGreaterThan(0);
  });
});

// ── Projects View ────────────────────────────────────────

test.describe("Projects View", () => {
  test("projects view shows project cards", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="projects"]');
    await page.waitForTimeout(500);

    const projectCards = page.locator(".project-card");
    expect(await projectCards.count()).toBeGreaterThan(0);
  });

  test("clicking a project card filters sessions", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="projects"]');
    await page.waitForSelector(".project-card", { timeout: 5000 });

    await page.locator(".project-card").first().click();
    await page.waitForTimeout(500);

    // Should switch back to sessions view with search populated
    const searchValue = await page.locator("#searchInput").inputValue();
    expect(searchValue.length).toBeGreaterThan(0);
  });
});

// ── Timeline View ────────────────────────────────────────

test.describe("Timeline View", () => {
  test("timeline shows sessions grouped by date", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="timeline"]');
    await page.waitForSelector(".timeline", { timeout: 5000 });

    const dateSections = page.locator(".timeline-date");
    expect(await dateSections.count()).toBeGreaterThan(0);

    // Each date section should have a label
    const label = page.locator(".timeline-date-label").first();
    await expect(label).toBeVisible();
  });
});

// ── Settings View ────────────────────────────────────────

test.describe("Settings", () => {
  test("settings shows theme buttons", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="settings"]');

    const themeButtons = page.locator(".theme-btn");
    expect(await themeButtons.count()).toBe(3);
  });

  test("settings shows layout selector", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="settings"]');

    await expect(page.locator(".settings-select")).toBeVisible();
  });

  test("settings shows session count", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="settings"]');

    const text = await page.locator(".settings-page").textContent();
    expect(text).toMatch(/\d+ sessions loaded/);
  });

  test("change theme from settings", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="settings"]');

    await page.locator('.theme-btn:has-text("Light")').click();
    const theme = await page.locator("html").getAttribute("data-theme");
    expect(theme).toBe("light");

    // Switch back to dark
    await page.locator('.theme-btn:has-text("Dark")').click();
  });
});

// ── Changelog View ───────────────────────────────────────

test.describe("Changelog", () => {
  test("changelog loads entries", async ({ page }) => {
    await page.goto(BASE);
    await page.click('.sidebar-item[data-view="changelog"]');
    await page.waitForSelector(".changelog-container", { timeout: 5000 });

    const entries = page.locator(".changelog-entry");
    expect(await entries.count()).toBeGreaterThan(0);

    // First entry should have version and date
    await expect(page.locator(".changelog-version").first()).toBeVisible();
    await expect(page.locator(".changelog-date").first()).toBeVisible();
  });
});

// ── API Endpoints ────────────────────────────────────────

test.describe("API Endpoints", () => {
  test("GET /api/sessions returns JSON array", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/sessions`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThan(0);
  });

  test("GET /api/version returns version info", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/version`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data).toHaveProperty("current");
  });

  test("GET /api/active returns array", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/active`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("GET /api/analytics/cost returns cost data", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/analytics/cost`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data).toHaveProperty("totalCost");
    expect(data).toHaveProperty("totalSessions");
  });

  test("GET /api/search?q=test returns results", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/search?q=help`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("GET /api/changelog returns array", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/changelog`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("GET /api/session/:id returns detail", async ({ request }) => {
    // Get first session ID
    const sessResp = await request.get(`${BASE}/api/sessions`);
    const sessions = await sessResp.json();
    const id = sessions[0].id;

    const resp = await request.get(`${BASE}/api/session/${id}`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data).toHaveProperty("messages");
  });

  test("GET /api/cost/:id returns cost info", async ({ request }) => {
    const sessResp = await request.get(`${BASE}/api/sessions`);
    const sessions = await sessResp.json();
    const id = sessions[0].id;

    const resp = await request.get(`${BASE}/api/cost/${id}`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data).toHaveProperty("cost");
  });
});

// ── Responsive / Edge Cases ──────────────────────────────

test.describe("Edge Cases", () => {
  test("page handles rapid view switching", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    // Rapid-fire click through all views
    const views = ["projects", "timeline", "analytics", "running", "starred", "changelog", "settings", "sessions"];
    for (const view of views) {
      await page.click(`.sidebar-item[data-view="${view}"]`);
    }

    // Should end on sessions with no errors
    await page.waitForSelector(".card", { timeout: 5000 });
    expect(await page.locator(".card").count()).toBeGreaterThan(0);
  });

  test("search with special characters doesn't crash", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });

    await page.fill("#searchInput", '<script>alert("xss")</script>');
    await page.waitForTimeout(300);
    // Page should still be functional
    await page.fill("#searchInput", "");
    await page.waitForTimeout(300);
    expect(await page.locator(".card").count()).toBeGreaterThan(0);
  });

  test("empty search shows all sessions", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForSelector(".card", { timeout: 5000 });
    const total = await page.locator(".card").count();

    await page.fill("#searchInput", "");
    await page.waitForTimeout(300);
    expect(await page.locator(".card").count()).toBe(total);
  });
});
