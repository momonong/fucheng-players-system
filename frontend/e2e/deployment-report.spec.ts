import { expect, test } from '@playwright/test'

const ids = `windows_edition memory virtualization disk_space install_location backup_directory
backup_write_and_restore docker_data_root wsl_version wsl_backend test_port direct_ports
docker_service ac_sleep cold_boot_recovery hibernate_policy windows_firewall_baseline
proxy_configuration firewall_egress_policy docker_engine compose_plugin app_image
docker_subnet project_health lan_vpn_subnet domain_dns cloudflare_tcp_7844
cloudflare_udp_7844 cloudflare_https registry_https ngrok_tcp_443 preview_https
domain_control public_ingress direct_tls`.split(/\s+/)

test('管理員在手機與桌面上傳、查看、複製及下載部署報告', async ({ page, context }) => {
  const payload = {
    schema_version: 1, checked_at: new Date().toISOString(),
    host: { name: 'Synthetic-Windows-Pro', windows: 'Windows 11 Pro', build: '26200', install_drive_free_gib: 50,
      docker_platform: 'linux/x86_64', docker_server_version: '28.5.1' },
    scope: { read_only_probes: true, created_report_directory: true, external_network_opt_in: false,
      container_execution: false, live_volume_access: false, compose_project: null, test_port: 8052,
      proposed_docker_subnet: '172.30.98.0/24' },
    summary: { PASS: ids.length, WARN: 0, FAIL: 0, NOT_TESTED: 0 },
    checks: ids.map(id => ({ id, status: 'PASS', reason: 'Synthetic only', evidence: 'No club host checked', next_action: 'Visit club host' })),
    recommendations: [{ candidate: 'Cloudflare Tunnel', status: 'NOT_TESTED', reason: 'No actual tunnel tested', next_action: 'Check on site' }],
    sources: ['https://example.org/synthetic'],
  }
  await page.goto('/admin')
  await page.getByLabel('帳號', { exact: true }).fill('e2e-admin')
  await page.getByLabel('密碼', { exact: true }).fill(process.env.FUCHENG_E2E_ADMIN_PASSWORD!)
  await page.getByRole('button', { name: '登入', exact: true }).click()
  await page.getByRole('link', { name: '系統狀態' }).click()
  await expect(page.getByRole('heading', { name: '部署檢查報告' })).toBeVisible()
  await expect(page.getByRole('button', { name: '上傳並取代最新報告' })).toBeVisible()
  await page.getByLabel('選擇部署檢查 JSON').setInputFiles({ name: 'synthetic-report.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(payload)) })
  await page.getByRole('button', { name: '上傳並取代最新報告' }).click()
  await expect(page.getByText('Synthetic-Windows-Pro')).toBeVisible()
  await expect(page.getByText('報告已儲存，且已納入資料庫備份。')).toBeVisible()
  await expect(page.getByText('Cloudflare Tunnel・NOT_TESTED')).toBeVisible()
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: '複製 Markdown' }).click()
  await expect(page.getByText('已複製 Markdown。')).toBeVisible()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(clipboard).toContain('Synthetic-Windows-Pro')
  for (const format of ['JSON', 'Markdown'] as const) {
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: `下載 ${format}` }).click()])
    expect(download.suggestedFilename()).toBe(format === 'JSON' ? 'deployment-report.json' : 'deployment-report.md')
  }
  if (test.info().project.name === 'mobile') {
    const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
    expect(sizes.document).toBeLessThanOrEqual(sizes.viewport + 2)
  }
})
