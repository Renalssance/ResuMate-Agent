import assert from 'node:assert/strict';
import { diagnoseMatches } from '../lib/field-matcher.js';

const profile = {
  sections: [
    {
      fields: [
        { key: 'projects.0.name', label: 'Project 1', value: '多Agent 智能旅行规划助手', aliases: [] },
        { key: 'projects.0.duration', label: 'Project Dates 1', value: '2025.01 - 2025.06', aliases: [] },
      ],
    },
  ],
};

const diagnostics = diagnoseMatches(profile, [
  { index: 0, tag: 'input', type: 'text', labelText: '项目名称' },
  { index: 1, tag: 'input', type: 'text', labelText: '起止时间' },
  { index: 2, tag: 'input', type: 'text', labelText: '项目链接' },
]);

assert.deepEqual(
  diagnostics.elements.map((item) => ({
    index: item.element.index,
    fieldKey: item.bestCandidate && item.bestCandidate.fieldKey,
    score: item.bestCandidate && item.bestCandidate.score,
    status: item.status,
  })),
  [
    { index: 0, fieldKey: 'projects.0.name', score: 4, status: 'candidate' },
    { index: 1, fieldKey: 'projects.0.duration', score: 4, status: 'candidate' },
    { index: 2, fieldKey: '', score: 0, status: 'no-candidate' },
  ],
);

assert.equal(diagnostics.fieldCount, 2);
assert.equal(diagnostics.valuedFieldCount, 2);
