import { test, expect } from '@playwright/test';

test('required local video studio controls are live', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', err => errors.push(err.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Ollama Video Studio' })).toBeVisible();

  const duration = page.getByTestId('duration-select');
  await expect(duration.locator('option')).toHaveCount(10);
  await expect(duration.locator('option').first()).toHaveText('1 minute');
  await expect(duration.locator('option').last()).toHaveText('10 minutes');

  const styles = page.getByTestId('narration-style-select');
  await expect(styles.locator('option')).toHaveCount(7);
  for (const label of ['Calm', 'Documentary', 'Warm', 'Inspirational', 'Emotional', 'Dramatic', 'Sermon']) {
    await expect(styles.locator('option', { hasText: label })).toHaveCount(1);
  }
  await styles.selectOption({ label: 'Dramatic' });
  await expect(styles).toHaveValue('Dramatic');
  await styles.selectOption({ label: 'Sermon' });
  await expect(styles).toHaveValue('Sermon');

  const source = page.getByTestId('media-source-select');
  await source.selectOption('wikimedia');
  await expect(source).toHaveValue('wikimedia');

  await expect(page.getByTestId('subtitle-controls')).toBeVisible();
  await expect(page.getByTestId('generate-button')).toBeVisible();
  expect(errors, `Active browser errors: ${errors.join(' | ')}`).toEqual([]);
});
