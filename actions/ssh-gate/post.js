"use strict"
const lib = require("./lib")

/** Main adımının kurduğu bütün geçici firewall'ları siler; silinemeyenlerin id'lerini döner. */
const run = async ({ env = process.env, client: injectedClient = null, sleep = lib.sleep } = {}) => {
  const ids = lib.parseIdList(env.STATE_firewall_ids)
  if (ids.length === 0) {
    return []
  }
  const client = injectedClient || lib.createClient(lib.input("hcloud-token", { required: true }, env))
  const failed = []
  for (const id of ids) {
    try {
      const removed = await lib.removeGate(client, id, { sleepFn: sleep })
      lib.log(removed ? `Geçici SSH firewall'u kaldırıldı (${id}).` : `Geçici SSH firewall'u zaten yok (${id}).`)
    } catch (error) {
      failed.push(id)
      // Temizlik hatası işi düşürmez: firewall'un süresi dolunca sonraki deploy onu siler.
      lib.warn(`Geçici SSH firewall'u ${id} kaldırılamadı: ${error.message}. Süresi dolunca sonraki deploy siler.`)
    }
  }
  return failed
}

module.exports = { run }

if (require.main === module) {
  run().catch((error) => lib.warn(`Geçici SSH firewall temizliği atlandı: ${error.message}`))
}
