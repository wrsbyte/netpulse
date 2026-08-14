import { test, expect, type ConsoleMessage, type Page } from '@playwright/test'

// End-to-end smoke test: load the real app served by netpulse-api and walk every tab, failing on
// ANY console error or uncaught exception. This is the layer that catches runtime breakage unit
// tests and `make check` can't — e.g. an ECharts series type not registered in the tree-shaken
// core (which silently crashed the Map with 'Cannot read properties of undefined').

const TABS = ['Dashboard', 'Routes', 'Map', 'Path', 'Raw data'] as const

function trackErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m: ConsoleMessage) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })
  page.on('pageerror', (e: Error) => errors.push(`pageerror: ${e.message}`))
  return errors
}

test('every tab renders without console errors', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'netpulse' })).toBeVisible()

  for (const tab of TABS) {
    await page.getByRole('tab', { name: tab }).click()
    // give charts a beat to run setOption (where the ECharts crash surfaced)
    await page.waitForTimeout(800)
    expect(page.getByRole('tab', { name: tab })).toBeTruthy()
  }
  expect(errors, `console errors while walking tabs:\n${errors.join('\n')}`).toEqual([])
})

test('dashboard shows live data, not placeholders', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  // Status KPI resolves to Online/Offline (not the '—' placeholder) once the first fetch lands.
  await expect(page.getByText(/^(Online|Offline)$/)).toBeVisible({ timeout: 15_000 })
  // The experience panel renders its four activity cards (not the loading state).
  await expect(page.getByText('Video calls', { exact: true })).toBeVisible({ timeout: 25_000 })
  await expect(page.getByText('Gathering data…')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('map renders a chart canvas without crashing', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Map' }).click()
  await expect(page.getByRole('heading', { name: 'Route map' })).toBeVisible({ timeout: 20_000 })
  // ECharts draws into a <canvas>; its presence proves setOption didn't throw.
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 20_000 })
  expect(errors, `map console errors:\n${errors.join('\n')}`).toEqual([])
})

test('routes tab shows the CDN and DNS panels', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Routes' }).click()
  await expect(page.getByRole('heading', { name: /CDN serving POP/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'DNS resolvers compared' })).toBeVisible()
  expect(errors).toEqual([])
})

test('routes aggregates traffic by named service, not raw IPs', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: 'Routes' }).click()
  const table = page.getByRole('table').filter({ hasText: 'Endpoints' })
  await expect(table).toBeVisible({ timeout: 15_000 })
  // The service table must have rows and none should be a bare IPv6 literal (the old wall of raw
  // endpoints). At least one named service (letters) must appear.
  const firstCol = table.locator('tbody tr td:first-child')
  await expect(firstCol.first()).toBeVisible({ timeout: 15_000 })
  const labels = await firstCol.allInnerTexts()
  expect(labels.length).toBeGreaterThan(0)
  expect(labels.some((t) => /[A-Za-z]{3,}/.test(t))).toBe(true)
  expect(labels.some((t) => t.includes('::'))).toBe(false)
})

test('experience panel rates the four activities', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Video calls', { exact: true })).toBeVisible({ timeout: 25_000 })
  for (const act of ['Browsing', 'Streaming', 'Gaming']) {
    await expect(page.getByText(act, { exact: true })).toBeVisible()
  }
})
