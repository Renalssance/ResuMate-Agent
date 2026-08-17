export const extensionDownload = {
  label: '下载插件',
  href: '/downloads/resumate-autofill-extension.zip',
  filename: 'resumate-autofill-extension.zip',
}

export const installSteps = [
  '打开 Chrome 或 Edge，进入 chrome://extensions。',
  '打开右上角开发者模式，点击“加载已解压的扩展程序”。',
  '解压下载包，选择解压后的文件夹完成安装。',
  '打开招聘申请页面，点击 ResuMate Autofill 插件图标。',
]

export const usageSteps = [
  '在插件设置里填写后端地址，并登录 ResuMate 账号。',
  '点击刷新，选择已解析并保存结构资料的简历。',
  '进入招聘表单页面，点击扫描页面。',
  '检查匹配字段，取消不想填写的项目。',
  '点击填充选中项，回到网页确认后手动提交。',
]

export const safetyNotes = [
  '只填充你勾选的字段。',
  '不会自动提交招聘申请。',
  '密码、验证码、文件上传等敏感字段会跳过。',
  '页面、简历或设置变化后，需要重新扫描再填充。',
]
