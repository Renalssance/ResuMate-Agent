export const extensionDownload = {
  label: '下载插件',
  href: '/downloads/resumate-autofill-extension.zip',
  filename: 'resumate-autofill-extension.zip',
}

export const extensionMeta = {
  name: 'ResuMate Autofill',
  version: '0.2.0',
  manifest: 'Manifest V3',
  backend: 'http://127.0.0.1:8000',
  profilesApi: '/api/autofill/profiles',
  sidePanel: 'sidepanel/sidepanel.html',
}

export const installSteps = [
  '解压下载包',
  '打开 chrome://extensions',
  '开启开发者模式',
  '加载解压后的插件目录',
]

export const usageSteps = [
  '在插件设置里填写后端地址，并登录 ResuMate 账号。',
  '在岗位页点击读取当前岗位，核对或粘贴正文后收藏。',
  '点击刷新，选择原简历或已确认的简历版本。',
  '进入招聘表单页面，点击扫描页面。',
  '检查匹配字段，取消不想填写的项目。',
  '点击填充选中项，回到网页确认后手动提交。',
]

export const extensionWorkflow = [
  {
    title: '连接账号',
    label: 'Settings',
    description: '填写后端地址并登录 ResuMate 账号。',
  },
  {
    title: '收藏当前岗位',
    label: 'Read & save',
    description: '主动读取可见正文，核对后收藏；受限页面可粘贴。',
  },
  {
    title: '选择简历版本',
    label: 'Version',
    description: '选择原简历或已确认版本，预览本次要填写的内容。',
  },
  {
    title: '扫描页面',
    label: 'Scan page',
    description: '在招聘表单页识别可填字段并预览匹配结果。',
  },
  {
    title: '填充选中项',
    label: 'Fill selected',
    description: '只写入勾选字段，提交仍由你手动完成。',
  },
]

export const safetyNotes = [
  '只填充勾选字段',
  '不会自动提交',
  '跳过密码、验证码和文件上传',
  '页面或简历版本变化后重新扫描',
  '填表不会自动生成投递记录',
]
