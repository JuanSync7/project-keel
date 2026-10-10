// title: Counter journey
// layer: frontend
// summary: Opens the built app in a headless browser, presses increment, and reads the new count.
import { expect, test } from '@playwright/test'

test('pressing increment raises the count by one', async ({ page }) => {
  await page.goto('/')
  const heading = page.getByRole('heading', { level: 1 })
  await expect(heading).toHaveText('hello: 0')
  await page.getByRole('button', { name: 'increment' }).click()
  await expect(heading).toHaveText('hello: 1')
})
