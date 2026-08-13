import assert from 'node:assert/strict';
import { matchLocally } from '../lib/field-matcher.js';

const profile = {
  id: 'resume:2',
  name: 'Zhu',
  sections: [
    {
      id: 'projects',
      label: 'Projects',
      fields: [
        { key: 'projects.0.name', label: 'Project 1', value: '多Agent 智能旅行规划助手', aliases: [] },
        { key: 'projects.0.role', label: 'Project Role 1', value: '后端开发', aliases: [] },
        { key: 'projects.0.duration', label: 'Project Dates 1', value: '2025.01 - 2025.06', aliases: [] },
        { key: 'projects.0.description', label: 'Project Description 1', value: '负责 Agent 编排、RAG 检索和行程生成。', aliases: [] },
      ],
    },
  ],
};

const response = matchLocally(profile, [
  { index: 0, tag: 'input', type: 'text', labelText: '项目名称' },
  { index: 1, tag: 'input', type: 'text', labelText: '项目角色' },
  { index: 2, tag: 'input', type: 'text', labelText: '起止时间' },
  { index: 3, tag: 'input', type: 'text', labelText: '项目链接' },
  { index: 4, tag: 'textarea', type: '', labelText: '描述' },
]);

assert.deepEqual(
  response.matches.map((item) => [item.fieldKey, item.elementIndex]),
  [
    ['projects.0.name', 0],
    ['projects.0.role', 1],
    ['projects.0.duration', 2],
    ['projects.0.description', 4],
  ],
);
