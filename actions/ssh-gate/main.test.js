"use strict"
const { describe, it, beforeEach } = require("node:test")
const assert = require("node:assert/strict")
const fs = require("fs")
const os = require("os")
const path = require("path")
const { HcloudError } = require("./lib")
const { run } = require("./main")
const post = require("./post")

const noSleep = async () => {}

const server = (id, ip, firewalls = []) => ({
  id,
  name: `srv-${id}`,
  public_net: { ipv4: { ip }, firewalls: firewalls.map((fid) => ({ id: fid, status: "applied" })) },
})

/** Yol desenleriyle yanıt veren sahte Hetzner istemcisi; çağrıları kaydeder. */
const fakeClient = (routes) => {
  const calls = []
  const handle = (method) => async (p, body) => {
    calls.push({ method, path: p, body })
    const route = routes.find((r) => r.method === method && r.match.test(p))
    if (!route) {
      throw new Error(`beklenmeyen istek: ${method} ${p}`)
    }
    return route.reply(p, body)
  }
  return { calls, get: handle("GET"), post: handle("POST"), del: handle("DELETE") }
}

const baseRoutes = (servers, gates = []) => [
  { method: "GET", match: /^\/firewalls\?label_selector=/, reply: () => ({ firewalls: gates }) },
  { method: "GET", match: /^\/servers\?/, reply: () => ({ servers }) },
]

let stateFile
const env = (extra = {}) => ({
  "INPUT_HCLOUD-TOKEN": "t",
  INPUT_HOSTS: "1.1.1.1,2.2.2.2",
  GITHUB_REPOSITORY: "Teamfluencer-Dev/teamfluencerapi",
  GITHUB_RUN_ID: "42",
  GITHUB_STATE: stateFile,
  ...extra,
})
const savedIds = () => {
  const lines = fs.readFileSync(stateFile, "utf8").trim().split("\n")
  return lines[lines.length - 1].replace("firewall_ids=", "")
}
const deps = (client) => ({ client, detectIp: async () => "4.4.4.4", sleep: noSleep, waitPort: async () => true, now: () => 1_000_000, random: () => "abcd" })

describe("main", () => {
  beforeEach(() => {
    stateFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "ssh-gate-")), "state")
    fs.writeFileSync(stateFile, "")
  })

  it("opens SSH only on servers that already have a base firewall and records the id", async () => {
    const client = fakeClient([
      ...baseRoutes([server(1, "1.1.1.1", [10]), server(2, "2.2.2.2")]),
      { method: "POST", match: /^\/firewalls$/, reply: () => ({ firewall: { id: 500 }, actions: [{ id: 1, status: "success" }] }) },
    ])

    const result = await run({ env: env(), ...deps(client) })

    const create = client.calls.find((c) => c.method === "POST")
    assert.deepEqual(create.body.apply_to, [{ type: "server", server: { id: 1 } }])
    assert.deepEqual(create.body.rules[0].source_ips, ["4.4.4.4/32"])
    assert.equal(create.body.labels.expires, String(1000 + 120 * 60))
    assert.equal(result.firewallId, 500)
    assert.equal(savedIds(), "500")
  })

  it("does nothing when no target has a base firewall", async () => {
    const client = fakeClient(baseRoutes([server(1, "1.1.1.1"), server(2, "2.2.2.2", [99])], [{ id: 99, labels: { expires: "9999999" } }]))

    const result = await run({ env: env(), ...deps(client) })

    assert.deepEqual(result.gated, [])
    assert.ok(!client.calls.some((c) => c.method === "POST"))
  })

  it("finds and removes a firewall whose create response was lost, then retries", async () => {
    let creates = 0
    const client = fakeClient([
      ...baseRoutes([server(1, "1.1.1.1", [10])]),
      {
        method: "POST",
        match: /^\/firewalls$/,
        reply: () => {
          creates += 1
          if (creates === 1) {
            throw new HcloudError(409, "uniqueness_error", "name is already used")
          }
          return { firewall: { id: 601 }, actions: [] }
        },
      },
      { method: "GET", match: /^\/firewalls\?name=/, reply: () => ({ firewalls: [{ id: 600 }] }) },
      { method: "GET", match: /^\/firewalls\/600$/, reply: () => ({ firewall: { id: 600, applied_to: [] } }) },
      { method: "DELETE", match: /^\/firewalls\/600$/, reply: () => ({}) },
    ])

    await run({ env: env({ INPUT_HOSTS: "1.1.1.1" }), ...deps(client) })

    assert.ok(client.calls.some((c) => c.method === "DELETE" && c.path === "/firewalls/600"))
    assert.equal(savedIds(), "601")
  })

  it("keeps a firewall it could not roll back in state so the post step removes it", async () => {
    let creates = 0
    const client = fakeClient([
      ...baseRoutes([server(1, "1.1.1.1", [10])]),
      {
        method: "POST",
        match: /^\/firewalls$/,
        reply: () => {
          creates += 1
          return creates === 1
            ? { firewall: { id: 700 }, actions: [{ id: 2, status: "error", error: { code: "resource_limit_exceeded", message: "max 5" } }] }
            : { firewall: { id: 701 }, actions: [] }
        },
      },
      {
        method: "GET",
        match: /^\/firewalls\/700$/,
        reply: () => {
          throw new HcloudError(500, "server_error", "down")
        },
      },
    ])

    await run({ env: env({ INPUT_HOSTS: "1.1.1.1" }), ...deps(client) })

    assert.equal(savedIds(), "700,701")
  })

  it("fails fast on bad inputs instead of looping or writing a NaN expiry", async () => {
    const client = fakeClient([])
    await assert.rejects(run({ env: env({ INPUT_HOSTS: " , " }), ...deps(client) }), /hosts boş/)
    await assert.rejects(run({ env: env({ "INPUT_TTL-MINUTES": "abc" }), ...deps(client) }), /ttl-minutes/)
    await assert.rejects(run({ env: env({ "INPUT_TTL-MINUTES": "5" }), ...deps(client) }), /ttl-minutes/)
    await assert.rejects(run({ env: env({ "INPUT_WAIT-SECONDS": "5m" }), ...deps(client) }), /wait-seconds/)
    assert.equal(client.calls.length, 0)
  })
})

describe("post", () => {
  it("removes every recorded firewall and reports the ones it could not remove", async () => {
    const client = fakeClient([
      { method: "GET", match: /^\/firewalls\/1$/, reply: () => ({ firewall: { id: 1, applied_to: [] } }) },
      { method: "DELETE", match: /^\/firewalls\/1$/, reply: () => ({}) },
      {
        method: "GET",
        match: /^\/firewalls\/2$/,
        reply: () => {
          throw new HcloudError(500, "server_error", "down")
        },
      },
    ])

    const failed = await post.run({ env: { STATE_firewall_ids: "1,2" }, client, sleep: noSleep })

    assert.deepEqual(failed, ["2"])
    assert.ok(client.calls.some((c) => c.method === "DELETE" && c.path === "/firewalls/1"))
  })

  it("does nothing without recorded firewalls", async () => {
    assert.deepEqual(await post.run({ env: {} }), [])
  })
})
