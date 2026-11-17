"use strict"
const lib = require("./lib")

/** Input'ları okur ve doğrular; hatalı değerle sessizce devam etmez. */
const readConfig = (env) => {
  const token = lib.input("hcloud-token", { required: true }, env)
  const hosts = lib.parseHosts(lib.input("hosts", {}, env))
  if (hosts.length === 0) {
    throw new Error("hosts boş: SSH yapılacak sunucuların IP'si ya da adı verilmeli (workflow env değişkenleri tanımlı mı?)")
  }
  // TTL'nin alt sınırı, uzun bir deploy sürerken başka bir çalışmanın bu firewall'u
  // "süresi dolmuş" sayıp silmesini önler.
  const waitSeconds = lib.parseIntInput("wait-seconds", lib.input("wait-seconds", { fallback: "300" }, env), { min: 0, max: 3600 })
  const ttlMinutes = lib.parseIntInput("ttl-minutes", lib.input("ttl-minutes", { fallback: "120" }, env), { min: 30, max: 1440 })
  return { token, hosts, waitSeconds, ttlMinutes }
}

const run = async ({
  env = process.env,
  client: injectedClient = null,
  detectIp = lib.detectPublicIpv4,
  sleep = lib.sleep,
  waitPort = lib.waitForPort,
  now = () => Date.now(),
  random = () => Math.random().toString(36).slice(2, 6),
} = {}) => {
  const config = readConfig(env)
  const client = injectedClient || lib.createClient(config.token)
  const state = lib.stateWriter(env)
  const nowSec = () => Math.floor(now() / 1000)

  try {
    await lib.cleanupExpired(client, nowSec(), { sleepFn: sleep })
  } catch (error) {
    lib.warn(`Eski geçici firewall temizliği atlandı: ${error.message}`)
  }

  const gateIds = new Set((await lib.listGateFirewalls(client)).map((fw) => fw.id))
  const targets = lib.resolveTargets(await lib.listServers(client), config.hosts)
  const { gated, open } = lib.splitByBaseFirewall(targets, gateIds)
  for (const server of open) {
    lib.warn(`${server.name} (${lib.serverIp(server)}) sunucusunda kalıcı Hetzner firewall'u yok; SSH kısıtlı değil, geçici firewall uygulanmadı.`)
  }
  if (gated.length === 0) {
    lib.log("Geçici SSH firewall'u gerekmiyor.")
    return { firewallId: null, gated: [] }
  }

  const ip = await detectIp()
  const repo = (env.GITHUB_REPOSITORY || "local").split("/").pop()
  const runId = env.GITHUB_RUN_ID || String(nowSec())
  const attempt = env.GITHUB_RUN_ATTEMPT || "1"
  const deadline = now() + config.waitSeconds * 1000
  const targetNames = gated.map((s) => s.name).join(", ")
  // Bu çalışmanın kurup henüz silemediği firewall'lar; post adımı hepsini siler.
  const pending = []
  const track = (id) => {
    pending.push(id)
    state.save(pending)
  }
  const untrack = (id) => {
    const index = pending.indexOf(id)
    if (index >= 0) {
      pending.splice(index, 1)
      state.save(pending)
    }
  }

  for (let tryNo = 1; ; tryNo += 1) {
    const name = lib.gateName({ repo, runId, attempt, suffix: random() })
    let firewallId = null
    try {
      const data = await client.post(
        "/firewalls",
        lib.gateBody({ name, ip, servers: gated, repo, runId, expiresAt: nowSec() + config.ttlMinutes * 60 }),
      )
      firewallId = data.firewall.id
      track(firewallId)
      await lib.waitActions(client, data.actions, { sleepFn: sleep })
      lib.log(`SSH ${ip}/32 için açıldı: ${targetNames} (firewall ${name})`)
      break
    } catch (error) {
      if (firewallId === null) {
        // İstek Hetzner'e ulaşıp yanıt kaybolmuş olabilir (ağ hatası, 5xx sonrası 409).
        const created = await lib.findFirewallByName(client, name).catch(() => null)
        if (created) {
          firewallId = created.id
          track(firewallId)
        }
      }
      if (firewallId !== null) {
        try {
          await lib.removeGate(client, firewallId, { sleepFn: sleep })
          untrack(firewallId)
        } catch (removeError) {
          lib.warn(`Yarım kalan firewall ${firewallId} silinemedi, post adımı yeniden deneyecek: ${removeError.message}`)
        }
      }
      if (!lib.isRetryable(error) || now() + 15000 > deadline) {
        throw error
      }
      const delay = Math.min(15000, 3000 * tryNo)
      lib.warn(`Geçici firewall kurulamadı (${error.message}); ${delay / 1000} sn sonra tekrar denenecek.`)
      await sleep(delay)
    }
  }

  for (const server of gated) {
    if (!(await waitPort(lib.serverIp(server), 22, { sleepFn: sleep }))) {
      lib.warn(`${server.name}:22 henüz yanıt vermiyor; deploy adımları kendi zaman aşımlarıyla devam edecek.`)
    }
  }
  return { firewallId: pending[pending.length - 1], gated: gated.map((s) => s.id), pending: [...pending] }
}

module.exports = { readConfig, run }

if (require.main === module) {
  run().catch((error) => {
    console.log(`::error::SSH gate: ${error.message}`)
    process.exit(1)
  })
}
