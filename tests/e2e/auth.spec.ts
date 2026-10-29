import { test, expect } from '@playwright/test'

test('注册密码不一致时保留输入并在浏览器阻止提交', async ({ page }) => {
  let submitted = false
  await page.route('**/auth/**', async route => {
    submitted = true
    await route.abort()
  })
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill('teaching-user')
  await page.getByLabel('密码', { exact: true }).fill('example-password')
  await page.getByLabel('确认密码', { exact: true }).fill('different-password')
  await page.getByRole('button', { name: '注册并开始使用' }).click()
  await expect(page.getByRole('alert')).toContainText('两次输入的密码不一致')
  await expect(page.getByLabel('用户名', { exact: true })).toHaveValue('teaching-user')
  expect(submitted).toBe(false)
})
