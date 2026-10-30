"""Synthetic supported ResumeProfile fields for real two-page PDF acceptance."""
from copy import deepcopy


def chinese_resume_content():
    content = {
        'resume': {
            'candidate_name': '林知远',
            'contact': {'email': 'lin.zhiyuan@example.test', 'phone': '13800000000', 'location': '上海'},
            'self_summary': '全栈开发工程师，关注可靠的业务流程、可解释的 AI 工具与清晰的产品体验。参与接口设计、数据建模、前后端联调和自动化测试，以能够复现的证据记录交付结果。',
            'education': [{
                'school': '示例科技大学', 'college': '计算机学院', 'degree': '本科', 'major': '软件工程',
                'years': '2020 - 2024', 'gpa': '3.7 / 4.0', 'rank': '前 10%',
                'lab': '软件系统实验室', 'research_direction': '分布式应用', 'advisor': '陈老师',
                'papers': ['面向协作流程的任务恢复实践'], 'courses': ['数据库系统', '计算机网络'],
                'achievements': ['优秀毕业设计'],
            }],
            'work_experience': [{
                'company': '示例企业数字化与智能协作平台研发中心（业务系统与开发者体验团队）',
                'title': '全栈开发工程师', 'duration': '2024.07 - 至今',
                'description': ('负责接口契约和数据库结构设计，与产品及前端同事核对异常路径。将长任务移至独立工作进程，保存进度与可恢复的任务状态。为实际出现的故障补充回归，记录问题、原因和修复证据。' * 3),
                'bullets': [{'raw_text': '独立要点：维护接口说明与新成员联调指引。'}],
                'technologies': ['Python', 'FastAPI', 'Vue', 'MySQL'],
                'metrics': [{'name': '吞吐', 'value': '3倍'}],
            }, {
                'company': '校园信息服务团队', 'title': '开发实习生', 'duration': '2023.07 - 2024.06',
                'description': '已审阅后的表述：参与信息查询页面与服务接口开发，维护可重复运行的联调样例。',
                'bullets': [{'raw_text': '旧要点不应复活'}],
                'metrics': [{'raw_text': '旧指标不应复活'}],
            }],
            'projects': [{
                'name': 'ResuMate 求职材料协作', 'role': '全栈开发', 'duration': '2026.09 - 2026.10',
                'description': ('建立岗位资料、简历版本、来源引用和用户审阅流程。保留固定输入及历史投递材料，支持取消、补问、并发保存与失败重试。为桌面和手机验证长文、错误与空状态，逐张检查真实页面截图。' * 3),
                'bullets': [{'raw_text': '项目独立要点：将开发决策与测试过程整理成教学文档。'}],
                'technologies': ['TypeScript', 'Celery', 'Redis', 'Playwright'],
            }, {
                'name': '已清空描述的练习项目', 'role': '协作者', 'description': '',
                'bullets': [{'raw_text': '已清空旧正文不应出现'}],
            }],
            'skills': [{'name': 'Python', 'category': '后端', 'proficiency_claim': '可独立开发业务接口'},
                       {'name': 'TypeScript / Vue', 'category': '前端'}, {'name': 'SQL', 'category': '数据建模'}],
            'achievements': [{'name': '校园软件设计实践奖', 'level': '校级', 'category': '工程实践'}],
            'certifications': ['软件设计师'], 'languages': ['中文：母语', '英语：技术文档阅读'],
            'quality': {'internal_marker': 'internal_only_marker'},
            'source_refs': [{'text': 'internal_only_marker'}],
        },
        'changes': [
            {'section': '/work_experience/1/description', 'status': 'edited', 'editedText': '已审阅后的表述：参与信息查询页面与服务接口开发，维护可重复运行的联调样例。'},
            {'section': '/projects/1/description', 'status': 'edited', 'editedText': ''},
        ],
    }
    return deepcopy(content)


def inspect_pdf(path, evidence_dir):
    """Fail on missing real fields; save every actual page for visual inspection."""
    import pymupdf
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(path) as document:
        text = '\n'.join(page.get_text() for page in document)
        compact = ''.join(text.split())
        for phrase in ['林知远', '计算机学院', '陈老师', '3.7 / 4.0', '前 10%', '软件系统实验室',
                       '分布式应用', '面向协作流程的任务恢复实践', '数据库系统', '优秀毕业设计',
                       '独立要点：维护接口说明与新成员联调指引。', '已审阅后的表述', '项目独立要点',
                       '软件设计师', '英语：技术文档阅读', '校园软件设计实践奖', '吞吐', '3倍']:
            assert ''.join(phrase.split()) in compact, f'Missing PDF content: {phrase}'
        for omitted in ['旧要点不应复活', '旧指标不应复活', '已清空旧正文不应出现', 'internal_only_marker']:
            assert omitted not in compact
        assert '\ufffd' not in text
        (evidence_dir / 'extracted-text.txt').write_text(text)
        for index, page in enumerate(document):
            page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(evidence_dir / f'page-{index + 1}.png')
        print(f'PDF pages={len(document)}, characters={len(text)}; evidence={evidence_dir}')
        assert len(document) == 2, 'Acceptance fixture should exercise a two-page resume'
