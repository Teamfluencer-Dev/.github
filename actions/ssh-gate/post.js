"use strict"
const { createClient, input, log, removeGate, warn } = require("./lib")

const run = async () => {
  const firewallId = (process.env.STATE_firewall_id || "").trim()
  if (!firewallId) {
    return
  }
  const removed = await removeGate(createClient(input("hcloud-token", { required: true })), firewallId)
  log(removed ? `Geçici SSH firewall'u kaldırıldı (${firewallId}).` : `Geçici SSH firewall'u zaten yok (${firewallId}).`)
}

// Temizlik hatası işi düşürmez: firewall'un süresi dolunca sonraki deploy onu siler.
run().catch((error) => warn(`Geçici SSH firewall'u kaldırılamadı: ${error.message}`))
