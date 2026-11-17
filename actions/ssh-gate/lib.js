"use strict"
/**
 * Hetzner SSH gate (TA-2252): deploy süresince yalnız bu runner'ın IPv4'üne port 22'yi açan
 * geçici bir Hetzner Cloud firewall kurar, iş bitince siler.
 *
 * Neden ayrı bir firewall: sunucuların kalıcı SSH izin listesi admin panelinden yönetilir.
 * Workflow o listeye yazsaydı, aynı anda koşan iki deploy (ya da admin kaydı) birbirinin IP'sini
 * silebilirdi (Hetzner `set_rules` bütün listeyi değiştirir). Her çalışma kendi firewall'unu
 * kurup sildiği için ortak bir listeye yazılmaz. Hetzner firewall'ları birleşir (union): bu
 * firewall yalnız izin ekler, sunucunun diğer kurallarına dokunmaz.
 */
const fs = require("fs")
const net = require("net")

const API = "https://api.hetzner.cloud/v1"
const PURPOSE = "gh-ssh-gate"
const IPV4_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/
const IP_SERVICES = ["https://api.ipify.org", "https://checkip.amazonaws.com", "https://ipv4.icanhazip.com"]

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const log = (message) => console.log(message)
const warn = (message) => console.log(`::warning::${message}`)

/** Action input'u: `INPUT_<AD>` (tire korunur, büyük harf). */
const input = (name, { required = false, fallback = "" } = {}) => {
  const value = (process.env[`INPUT_${name.toUpperCase()}`] || "").trim()
  if (!value && required) {
    throw new Error(`Gerekli input yok: ${name}`)
  }
  return value || fallback
}

/** Post adımı STATE_<ad> ortam değişkeninden okur. */
const saveState = (name, value) => {
  if (process.env.GITHUB_STATE) {
    fs.appendFileSync(process.env.GITHUB_STATE, `${name}=${value}\n`)
  }
}

const isIpv4 = (value) => {
  const match = IPV4_RE.exec(value)
  return Boolean(match) && match.slice(1).every((octet) => Number(octet) <= 255)
}

class HcloudError extends Error {
  constructor(status, code, message) {
    super(`Hetzner API ${status} ${code}: ${message}`)
    this.status = status
    this.code = code
  }
}

const createClient = (token, { fetchImpl = fetch, sleepFn = sleep } = {}) => {
  const request = async (method, path, body) => {
    for (let attempt = 1; ; attempt += 1) {
      const response = await fetchImpl(`${API}${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      if (response.status === 204) {
        return {}
      }
      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        return data
      }
      const error = new HcloudError(
        response.status,
        (data.error && data.error.code) || "unknown",
        (data.error && data.error.message) || response.statusText,
      )
      if ((response.status === 429 || response.status >= 500) && attempt < 4) {
        await sleepFn(2000 * attempt)
        continue
      }
      throw error
    }
  }
  return {
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body),
    del: (path) => request("DELETE", path),
  }
}

/** Sunucu limiti, kilit ve hız sınırı gibi geçici hatalar beklenip tekrar denenir. */
const isRetryable = (error) =>
  error instanceof HcloudError &&
  ([409, 423, 429].includes(error.status) || error.status >= 500 || /limit|conflict|locked|timeout/.test(error.code))

const parseHosts = (raw) => [...new Set(String(raw).split(/[\s,]+/).map((s) => s.trim()).filter(Boolean))]

const listServers = async (client) => {
  const servers = []
  for (let page = 1; page; ) {
    const data = await client.get(`/servers?per_page=50&page=${page}`)
    servers.push(...(data.servers || []))
    page = (data.meta && data.meta.pagination && data.meta.pagination.next_page) || null
  }
  return servers
}

const serverIp = (server) => (server.public_net && server.public_net.ipv4 && server.public_net.ipv4.ip) || ""

/** Host'ları (public IPv4 ya da sunucu adı) Hetzner sunucularıyla eşler; bilinmeyen host hatadır. */
const resolveTargets = (servers, hosts) => {
  const targets = hosts.map((host) => {
    const server = servers.find((s) => serverIp(s) === host || s.name === host)
    if (!server) {
      throw new Error(`Hetzner projesinde "${host}" adresli ya da adlı sunucu yok`)
    }
    return server
  })
  return [...new Map(targets.map((s) => [s.id, s])).values()]
}

/**
 * Hiç firewall'u olmayan sunucuya geçici firewall uygulamak 22 dışındaki bütün gelen trafiği
 * keser (firewall'lu sunucuda yalnız izin verilen trafik geçer). Böyle sunucularda SSH zaten
 * herkese açık sayılır; onlara dokunulmaz.
 */
const splitByBaseFirewall = (servers) => {
  const hasFirewall = (s) => ((s.public_net && s.public_net.firewalls) || []).length > 0
  return { gated: servers.filter(hasFirewall), open: servers.filter((s) => !hasFirewall(s)) }
}

const detectPublicIpv4 = async ({ fetchImpl = fetch, services = IP_SERVICES } = {}) => {
  for (const url of services) {
    try {
      const response = await fetchImpl(url, { signal: AbortSignal.timeout(5000) })
      const ip = (await response.text()).trim()
      if (response.ok && isIpv4(ip)) {
        return ip
      }
    } catch (_) {
      // sıradaki servise geç
    }
  }
  throw new Error("Runner'ın public IPv4 adresi bulunamadı")
}

const labelValue = (value) =>
  String(value).replace(/[^a-zA-Z0-9._-]/g, "-").replace(/^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$/g, "").slice(0, 63)

const gateName = ({ repo, runId, attempt, suffix }) =>
  `gh-ssh-${repo}-${runId}-${attempt}-${suffix}`.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 63)

const gateBody = ({ name, ip, servers, repo, runId, expiresAt }) => ({
  name,
  labels: {
    purpose: PURPOSE,
    repo: labelValue(repo),
    run_id: labelValue(runId),
    expires: String(expiresAt),
  },
  rules: [
    {
      direction: "in",
      protocol: "tcp",
      port: "22",
      source_ips: [`${ip}/32`],
      destination_ips: [],
      description: `GitHub Actions ${repo} run ${runId}`.slice(0, 255),
    },
  ],
  apply_to: servers.map((s) => ({ type: "server", server: { id: s.id } })),
})

const waitActions = async (client, actions, { timeoutMs = 120000, sleepFn = sleep } = {}) => {
  const deadline = Date.now() + timeoutMs
  for (const action of actions || []) {
    let current = action
    while (current.status === "running") {
      if (Date.now() > deadline) {
        throw new HcloudError(504, "timeout", `action ${current.id} bitmedi`)
      }
      await sleepFn(1000)
      current = (await client.get(`/actions/${current.id}`)).action
    }
    if (current.status === "error") {
      const error = current.error || {}
      throw new HcloudError(422, error.code || "action_failed", error.message || `action ${current.id}`)
    }
  }
}

/** Firewall'u sunuculardan ayırır ve siler. Zaten yoksa false döner. */
const removeGate = async (client, firewallId, { sleepFn = sleep } = {}) => {
  let firewall
  try {
    firewall = (await client.get(`/firewalls/${firewallId}`)).firewall
  } catch (error) {
    if (error.status === 404) {
      return false
    }
    throw error
  }
  const appliedTo = (firewall.applied_to || [])
    .filter((resource) => resource.type === "server")
    .map((resource) => ({ type: "server", server: { id: resource.server.id } }))
  if (appliedTo.length > 0) {
    const data = await client.post(`/firewalls/${firewallId}/actions/remove_from_resources`, { remove_from: appliedTo })
    await waitActions(client, data.actions, { sleepFn })
  }
  for (let attempt = 1; ; attempt += 1) {
    try {
      await client.del(`/firewalls/${firewallId}`)
      return true
    } catch (error) {
      if (error.status === 404) {
        return true
      }
      if (attempt >= 5) {
        throw error
      }
      await sleepFn(3000)
    }
  }
}

/** İptal edilen ya da post adımı çalışamayan işlerden kalan, süresi dolmuş geçici firewall'ları siler. */
const cleanupExpired = async (client, nowSec, { sleepFn = sleep } = {}) => {
  const data = await client.get(`/firewalls?label_selector=${encodeURIComponent(`purpose=${PURPOSE}`)}&per_page=50`)
  const expired = (data.firewalls || []).filter((fw) => Number((fw.labels && fw.labels.expires) || 0) < nowSec)
  let removed = 0
  for (const fw of expired) {
    try {
      await removeGate(client, fw.id, { sleepFn })
      removed += 1
      log(`Süresi dolmuş geçici firewall silindi: ${fw.name}`)
    } catch (error) {
      warn(`${fw.name} silinemedi: ${error.message}`)
    }
  }
  return removed
}

const tcpProbe = (host, port, timeoutMs) =>
  new Promise((resolve) => {
    const socket = net.connect({ host, port })
    const done = (ok) => {
      socket.destroy()
      resolve(ok)
    }
    socket.setTimeout(timeoutMs, () => done(false))
    socket.once("connect", () => done(true))
    socket.once("error", () => done(false))
  })

const waitForPort = async (host, port, { attempts = 10, sleepFn = sleep, probe = tcpProbe } = {}) => {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    if (await probe(host, port, 5000)) {
      return true
    }
    if (attempt < attempts) {
      await sleepFn(3000)
    }
  }
  return false
}

module.exports = {
  PURPOSE,
  HcloudError,
  cleanupExpired,
  createClient,
  detectPublicIpv4,
  gateBody,
  gateName,
  input,
  isIpv4,
  isRetryable,
  listServers,
  log,
  parseHosts,
  removeGate,
  resolveTargets,
  saveState,
  serverIp,
  sleep,
  splitByBaseFirewall,
  waitActions,
  waitForPort,
  warn,
}
