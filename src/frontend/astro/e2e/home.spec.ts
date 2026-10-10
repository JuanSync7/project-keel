// title: Home page journey
// layer: frontend
// summary: Opens the built site's home page in a headless browser and reads what a visitor sees.
//
// The base path comes from astro.config.mjs itself, so the journey opens the
// root the build was made for (PUBLIC_BASE_PATH included). The /api-fed island
// is not asserted: with no backend running it shows its error panel.
import { expect, test } from '@playwright/test'
import astroConfig from '../astro.config.mjs'

test('the home page has a title and shows the conventions section', async ({ page }) => {
  await page.goto(astroConfig.base ?? '/')
  await expect(page).toHaveTitle(/\S/)
  await expect(
    page.getByRole('heading', { name: 'The conventions everything rests on' }),
  ).toBeVisible()
})
