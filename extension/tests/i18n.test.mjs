import assert from 'node:assert/strict';
import { LANGUAGES, defaultLanguage, normalizeLanguage, t } from '../lib/i18n.js';

assert.deepEqual(LANGUAGES, ['zh', 'en']);

assert.equal(normalizeLanguage('zh'), 'zh');
assert.equal(normalizeLanguage('en'), 'en');
assert.equal(normalizeLanguage('fr'), 'en');
assert.equal(normalizeLanguage(''), 'en');
assert.equal(defaultLanguage('zh-CN'), 'zh');
assert.equal(defaultLanguage('zh-Hant'), 'zh');
assert.equal(defaultLanguage('en-US'), 'en');
assert.equal(defaultLanguage(''), 'en');

assert.equal(t('en', 'actions.scanPage'), 'Scan page');
assert.equal(t('zh', 'actions.scanPage'), '扫描页面');
assert.equal(t('en', 'profile.fieldCount', { count: 3 }), '3 fields');
assert.equal(t('zh', 'profile.savedFieldCount', { count: 3 }), '已保存 3 个字段');
assert.equal(t('en', 'resume.heading'), 'Stored resume');
assert.equal(t('zh', 'resume.heading'), '已存储简历');
assert.equal(t('en', 'resume.noResumes'), 'No stored resumes yet. Upload and parse a resume in ResuMate first.');
assert.equal(t('zh', 'resume.noResumes'), '还没有已存储简历。请先在 ResuMate 上传并解析简历。');
assert.equal(t('zh', 'missing.key'), 'missing.key');
assert.equal(t('fr', 'actions.fillSelected'), 'Fill selected');
