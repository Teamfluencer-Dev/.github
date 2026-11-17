"use strict"
const {
  cleanupExpired,
  createClient,
  detectPublicIpv4,
  gateBody,
  gateName,
  input,
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
} = require("./lib")

const run = async () => {
  const client = createClient(input("hcloud-token", { required: true }))
  const hosts = parseHosts(input("hosts", { required: true }))
  const waitSeconds = Number(input("wait-seconds", { fallback: "300" }))
  const ttlMinutes = Number(input("ttl-minutes", { fallback: "120" }))

  const { gated, open } = splitByBaseFirewall(resolveTargets(await listServers(client), hosts))
  for (const server of open) {
    warn(`${server.name} (${serverIp(server)}) sunucusunda Hetzner firewall'u yok; SSH kısıtlı değil, geçici firewall uygulanmadı.`)
  }
  if (gated.length === 0) {
    log("Geçici SSH firewall'u gerekmiyor.")
    return
  }

  const nowSec = () => Math.floor(Date.now() / 1000)
  try {
    await cleanupExpired(client, nowSec())
  } catch (error) {
    warn(`Eski geçici firewall temizliği atlandı: ${error.message}`)
  }

  const ip = await detectPublicIpv4()
  const repo = (process.env.GITHUB_REPOSITORY || "local").split("/").pop()
  const runId = process.env.GITHUB_RUN_ID || String(nowSec())
  const attempt = process.env.GITHUB_RUN_ATTEMPT || "1"
  const deadline = Date.now() + waitSeconds * 1000
  const targetNames = gated.map((s) => s.name).join(", ")

  for (let tryNo = 1; ; tryNo += 1) {
    const name = gateName({ repo, runId, attempt, suffix: Math.random().toString(36).slice(2, 6) })
    let firewallId = null
    try {
      const data = await client.post(
        "/firewalls",
        gateBody({ name, ip, servers: gated, repo, runId, expiresAt: nowSec() + ttlMinutes * 60 }),
      )
      firewallId = data.firewall.id
      // İş bu noktadan sonra iptal edilse de post adımı firewall'u silebilsin.
      saveState("firewall_id", firewallId)
      await waitActions(client, data.actions)
      log(`SSH ${ip}/32 için açıldı: ${targetNames} (firewall ${name})`)
      break
    } catch (error) {
      if (firewallId) {
        await removeGate(client, firewallId).catch((e) => warn(`Yarım kalan firewall silinemedi: ${e.message}`))
        saveState("firewall_id", "")
      }
      if (!isRetryable(error) || Date.now() + 15000 > deadline) {
        throw error
      }
      const delay = Math.min(15000, 3000 * tryNo)
      warn(`Geçici firewall kurulamadı (${error.message}); ${delay / 1000} sn sonra tekrar denenecek.`)
      await sleep(delay)
    }
  }

  for (const server of gated) {
    if (!(await waitForPort(serverIp(server), 22))) {
      warn(`${server.name}:22 henüz yanıt vermiyor; deploy adımları kendi zaman aşımlarıyla devam edecek.`)
    }
  }
}

run().catch((error) => {
  console.log(`::error::SSH gate: ${error.message}`)
  process.exit(1)
})
