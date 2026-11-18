"use strict"
const { describe, it } = require("node:test")
const assert = require("node:assert/strict")
const {
  HcloudError,
  cleanupExpired,
  createClient,
  detectPublicIpv4,
  gateBody,
  gateName,
  isRetryable,
  parseHosts,
  parseIdList,
  parseIntInput,
  removeGate,
  resolveTargets,
  splitByBaseFirewall,
  waitActions,
  waitForPort,
} = require("./lib")

const noSleep = async () => {}

const server = (id, name, ip, firewalls = []) => ({
  id,
  name,
  public_net: { ipv4: { ip }, firewalls: firewalls.map((fid) => ({ id: fid, status: "applied" })) },
})

/** get/post/del çağrılarını kaydeden, yanıtları yol ile eşleyen sahte istemci. */
const fakeClient = (routes) => {
  const calls = []
  const handle = (method) => async (path, body) => {
    calls.push({ method, path, body })
    const handler = routes[`${method} ${path}`]
    if (handler === undefined) {
      throw new Error(`beklenmeyen istek: ${method} ${path}`)
    }
    return typeof handler === "function" ? handler(body) : handler
  }
  return { calls, get: handle("GET"), post: handle("POST"), del: handle("DELETE") }
}

describe("hosts", () => {
  it("splits on commas and whitespace and drops duplicates", () => {
    assert.deepEqual(parseHosts(" 1.1.1.1, 2.2.2.2\n1.1.1.1 ,,"), ["1.1.1.1", "2.2.2.2"])
  })

  it("matches by public IPv4 or server name and fails on an unknown host", () => {
    const servers = [server(1, "teamfluencer-api", "1.1.1.1"), server(2, "teamfluencer-green", "2.2.2.2")]
    assert.deepEqual(resolveTargets(servers, ["2.2.2.2", "teamfluencer-api", "1.1.1.1"]).map((s) => s.id), [2, 1])
    assert.throws(() => resolveTargets(servers, ["9.9.9.9"]), /9\.9\.9\.9/)
  })

  it("never gates a server without a firewall (it would block all other inbound traffic)", () => {
    const { gated, open } = splitByBaseFirewall([server(1, "a", "1.1.1.1", [10]), server(2, "b", "2.2.2.2")])
    assert.deepEqual(gated.map((s) => s.id), [1])
    assert.deepEqual(open.map((s) => s.id), [2])
  })

  it("does not count another run's gate firewall as a base firewall", () => {
    const servers = [server(1, "a", "1.1.1.1", [10, 99]), server(2, "b", "2.2.2.2", [99])]
    const { gated, open } = splitByBaseFirewall(servers, new Set([99]))
    assert.deepEqual(gated.map((s) => s.id), [1])
    assert.deepEqual(open.map((s) => s.id), [2])
  })
})

describe("gate firewall", () => {
  it("opens only TCP 22 for the runner IP, applied to the target servers", () => {
    const body = gateBody({
      name: "gh-ssh-x",
      ip: "4.4.4.4",
      servers: [server(1, "a", "1.1.1.1", [10])],
      repo: "teamfluencerapi",
      runId: "123",
      expiresAt: 1700000000,
    })
    assert.deepEqual(body.rules, [{
      direction: "in",
      protocol: "tcp",
      port: "22",
      source_ips: ["4.4.4.4/32"],
      destination_ips: [],
      description: "GitHub Actions teamfluencerapi run 123",
    }])
    assert.deepEqual(body.apply_to, [{ type: "server", server: { id: 1 } }])
    assert.deepEqual(body.labels, { purpose: "gh-ssh-gate", repo: "teamfluencerapi", run_id: "123", expires: "1700000000" })
  })

  it("builds a valid, bounded firewall name", () => {
    const name = gateName({ repo: "Teamfluencer_API.long".repeat(5), runId: "19283746", attempt: "2", suffix: "ab12" })
    assert.ok(name.length <= 63)
    assert.match(name, /^gh-ssh-[a-z0-9-]+$/)
  })
})

describe("inputs", () => {
  it("accepts integers in range and rejects everything else", () => {
    assert.equal(parseIntInput("wait-seconds", " 300 ", { min: 0, max: 3600 }), 300)
    for (const bad of ["", "abc", "1.5", "-1", "3601", "5m"]) {
      assert.throws(() => parseIntInput("wait-seconds", bad, { min: 0, max: 3600 }), /wait-seconds/)
    }
  })

  it("parses the stored firewall id list", () => {
    assert.deepEqual(parseIdList("12, 34,,x"), ["12", "34"])
    assert.deepEqual(parseIdList(undefined), [])
  })
})

describe("hetzner client", () => {
  it("retries on 5xx, then returns the body", async () => {
    let n = 0
    const fetchImpl = async () => {
      n += 1
      return n === 1
        ? { ok: false, status: 503, statusText: "x", json: async () => ({ error: { code: "unavailable", message: "busy" } }) }
        : { ok: true, status: 200, json: async () => ({ servers: [] }) }
    }
    const client = createClient("t", { fetchImpl, sleepFn: noSleep })
    assert.deepEqual(await client.get("/servers"), { servers: [] })
    assert.equal(n, 2)
  })

  it("throws a typed error on 4xx without retrying", async () => {
    let n = 0
    const fetchImpl = async () => {
      n += 1
      return { ok: false, status: 422, statusText: "x", json: async () => ({ error: { code: "invalid_input", message: "bad" } }) }
    }
    const client = createClient("t", { fetchImpl, sleepFn: noSleep })
    await assert.rejects(client.post("/firewalls", {}), (e) => e instanceof HcloudError && e.code === "invalid_input")
    assert.equal(n, 1)
  })

  it("retries network errors, then raises a retryable network error", async () => {
    let n = 0
    const fetchImpl = async () => {
      n += 1
      throw new TypeError("fetch failed")
    }
    const client = createClient("t", { fetchImpl, sleepFn: noSleep })
    await assert.rejects(client.get("/servers"), (e) => e.code === "network" && isRetryable(e))
    assert.equal(n, 4)
  })

  it("treats limits, locks and rate limits as retryable", () => {
    assert.equal(isRetryable(new HcloudError(403, "resource_limit_exceeded", "")), true)
    assert.equal(isRetryable(new HcloudError(423, "locked", "")), true)
    assert.equal(isRetryable(new HcloudError(409, "uniqueness_error", "")), true)
    assert.equal(isRetryable(new HcloudError(422, "invalid_input", "")), false)
    assert.equal(isRetryable(new Error("x")), false)
  })
})

describe("actions", () => {
  it("polls a running action until it succeeds", async () => {
    const client = fakeClient({ "GET /actions/5": { action: { id: 5, status: "success" } } })
    await waitActions(client, [{ id: 5, status: "running" }], { sleepFn: noSleep })
    assert.equal(client.calls.length, 1)
  })

  it("raises the Hetzner error of a failed action", async () => {
    const client = fakeClient({})
    await assert.rejects(
      waitActions(client, [{ id: 6, status: "error", error: { code: "resource_limit_exceeded", message: "max 5" } }]),
      (e) => e.code === "resource_limit_exceeded",
    )
  })
})

describe("cleanup", () => {
  it("detaches the firewall from its servers before deleting it", async () => {
    const client = fakeClient({
      "GET /firewalls/7": { firewall: { id: 7, applied_to: [{ type: "server", server: { id: 1 } }] } },
      "POST /firewalls/7/actions/remove_from_resources": { actions: [{ id: 8, status: "success" }] },
      "DELETE /firewalls/7": {},
    })
    assert.equal(await removeGate(client, 7, { sleepFn: noSleep }), true)
    assert.deepEqual(client.calls.map((c) => `${c.method} ${c.path}`), [
      "GET /firewalls/7",
      "POST /firewalls/7/actions/remove_from_resources",
      "DELETE /firewalls/7",
    ])
    assert.deepEqual(client.calls[1].body, { remove_from: [{ type: "server", server: { id: 1 } }] })
  })

  it("returns false when the firewall is already gone", async () => {
    const client = fakeClient({
      "GET /firewalls/7": () => {
        throw new HcloudError(404, "not_found", "x")
      },
    })
    assert.equal(await removeGate(client, 7), false)
  })

  it("removes only expired gate firewalls", async () => {
    const client = fakeClient({
      "GET /firewalls?label_selector=purpose%3Dgh-ssh-gate&per_page=50": {
        firewalls: [
          { id: 1, name: "old", labels: { purpose: "gh-ssh-gate", expires: "100" } },
          { id: 2, name: "live", labels: { purpose: "gh-ssh-gate", expires: "300" } },
        ],
      },
      "GET /firewalls/1": { firewall: { id: 1, applied_to: [] } },
      "DELETE /firewalls/1": {},
    })
    assert.equal(await cleanupExpired(client, 200, { sleepFn: noSleep }), 1)
    assert.ok(!client.calls.some((c) => c.path.startsWith("/firewalls/2")))
  })
})

describe("runner IP and port", () => {
  it("falls back to the next service and ignores a non-IPv4 answer", async () => {
    const answers = { a: "<html>", b: "5.6.7.8\n" }
    const fetchImpl = async (url) => ({ ok: true, text: async () => answers[url] })
    assert.equal(await detectPublicIpv4({ fetchImpl, services: ["a", "b"] }), "5.6.7.8")
  })

  it("waits until the port answers", async () => {
    let n = 0
    const probe = async () => {
      n += 1
      return n === 3
    }
    assert.equal(await waitForPort("1.1.1.1", 22, { attempts: 5, sleepFn: noSleep, probe }), true)
    assert.equal(n, 3)
  })
})
