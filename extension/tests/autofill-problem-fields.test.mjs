import assert from 'node:assert/strict';
import { matchLocally } from '../lib/field-matcher.js';

const profile = {
  sections: [
    {
      fields: [
        { key: 'application.emergency_contact_phone', label: 'Emergency Phone', value: '13800000001', aliases: ['紧急联系电话'] },
        { key: 'application.expected_city', label: 'Expected City', value: '上海', aliases: ['期望城市'] },
        { key: 'application.id_number', label: 'ID Number', value: '31010119990101001X', aliases: ['身份证号'] },
        { key: 'education.0.college', label: 'College 1', value: '信息科学与技术学院', aliases: ['学院'] },
        { key: 'education.0.rank', label: 'Rank 1', value: '前10%', aliases: ['成绩排名'] },
        { key: 'education.0.gpa', label: 'GPA 1', value: '3.83/4.00', aliases: ['GPA'] },
        { key: 'education.0.research_direction', label: 'Research Direction 1', value: '智能网络', aliases: ['研究方向'] },
        { key: 'education.0.papers', label: 'Papers 1', value: 'Graph RAG for Recruiting', aliases: ['论文'] },
      ],
    },
  ],
};

const response = matchLocally(profile, [
  { index: 0, tag: 'input', type: 'tel', labelText: '紧急联系人电话' },
  { index: 1, tag: 'input', type: 'text', labelText: '期望工作城市' },
  { index: 2, tag: 'input', type: 'text', labelText: '院系' },
  { index: 3, tag: 'select', type: 'select-one', labelText: '成绩排名' },
  { index: 4, tag: 'input', type: 'text', labelText: 'GPA' },
  { index: 5, tag: 'input', type: 'text', labelText: '研究方向' },
  { index: 6, tag: 'textarea', type: '', labelText: '论文' },
  { index: 7, tag: 'input', type: 'text', labelText: '身份证号' },
]);

assert.deepEqual(
  response.matches.map((item) => [item.fieldKey, item.elementIndex]),
  [
    ['application.emergency_contact_phone', 0],
    ['application.expected_city', 1],
    ['education.0.college', 2],
    ['education.0.rank', 3],
    ['education.0.gpa', 4],
    ['education.0.research_direction', 5],
    ['education.0.papers', 6],
    ['application.id_number', 7],
  ],
);
